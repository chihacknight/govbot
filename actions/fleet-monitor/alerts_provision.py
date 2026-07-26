"""Apply the committed alerting artifacts to a real Grafana stack.

Grafana Cloud has no filesystem to drop provisioning files into, so the
committed YAML reaches a stack through the provisioning API. This module is that
path: read ``alerting/*.yaml``, resolve their placeholders, and PUT the result.

Two things here are deliberate and easy to get wrong:

* **The notification policy is grafted, never replaced.** Grafana's policy API
  has no notion of a partial tree — a PUT to ``/policies`` swaps the whole root.
  Applying our own root to the maintainers' stack would silently redirect every
  alert they already run to this contact point, so the fleet's route is inserted
  as a child of whatever root is already there.
* **Every write carries ``X-Disable-Provenance``.** Without it Grafana marks
  API-provisioned resources read-only in the UI, and the first maintainer who
  tries to mute a rule or fix a webhook finds a greyed-out form and no
  explanation.
"""

import datetime
import json
import re
import time

import yaml

from alerting import (CONTACT_POINT, CONTACT_POINTS_FILE, EVAL_INTERVAL, FOLDER,
                      FOLDER_UID, POLICY_FILE, RULES_FILE, UnresolvedPlaceholder,
                      PLACEHOLDER)
from http_util import RequestFailed, request_with_retry

# Editable in the UI after provisioning. The alternative is a maintainer meeting
# a locked form the first time they try to silence something.
#
# The trade-off, worth stating: nothing then stops an Editor on the stack from
# repointing the Slack webhook or deleting the fleet's route, and provisioning is
# a manual command with no scheduled re-apply, so such drift persists until
# someone re-runs it. Re-running is the remedy, and it is cheap.
PROVENANCE = {"X-Disable-Provenance": "true"}

DURATION = re.compile(r"^(\d+)([smh])$")


def _seconds(duration) -> int:
    """A Grafana duration string as seconds; the rule-group API takes a number.

    Raises a `RuntimeError` naming the value rather than a `KeyError` or a
    `TypeError` from the middle of a parse: this runs after the folder and the
    contact points have already been written, so the failure a maintainer sees
    has to say which value was wrong, not print a traceback over a half-applied
    stack.
    """
    if isinstance(duration, int):
        return duration
    match = DURATION.match(str(duration))
    if not match:
        raise RuntimeError(
            f"cannot read {duration!r} as an evaluation interval; "
            "use a plain number of seconds or <int>s / <int>m / <int>h"
        )
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2)]


class Stack:
    """The subset of Grafana's API this needs, over the shared retry helper."""

    def __init__(self, base, token, sleep=time.sleep):
        self.base = base.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.sleep = sleep

    def get(self, path):
        body = request_with_retry(
            f"{self.base}{path}", headers=self.headers, sleep=self.sleep
        )
        return json.loads(body)

    def find(self, path):
        """GET, or None when the resource isn't there yet."""
        try:
            return self.get(path)
        except RequestFailed as e:
            if e.status == 404:
                return None
            raise

    def write(self, path, body, method="POST"):
        return request_with_retry(
            f"{self.base}{path}",
            data=json.dumps(body).encode(),
            headers={**self.headers, "Content-Type": "application/json", **PROVENANCE},
            method=method,
            sleep=self.sleep,
        )

    def delete(self, path):
        return request_with_retry(
            f"{self.base}{path}",
            headers={**self.headers, **PROVENANCE},
            method="DELETE",
            sleep=self.sleep,
        )


def resolve_datasource_uid(stack) -> str:
    """The stack's own Prometheus datasource uid.

    Not committed, because a uid belongs to one stack and these files have to
    apply to any of them. Discovered rather than demanded, so provisioning a
    fresh stack is one command — but never guessed: picking the wrong one of
    several provisions three rules that evaluate against nothing, forever, while
    reporting perfect health.
    """
    candidates = [d for d in stack.get("/api/datasources") if d.get("type") == "prometheus"]
    if not candidates:
        raise RuntimeError(
            "no Prometheus datasource on this stack; add one, or set "
            "GRAFANA_METRICS_DATASOURCE_UID"
        )
    if len(candidates) > 1:
        names = ", ".join(f"{d['name']} ({d['uid']})" for d in candidates)
        raise RuntimeError(
            f"{len(candidates)} Prometheus datasources on this stack — {names}. "
            "Set GRAFANA_METRICS_DATASOURCE_UID to the one holding the fleet metrics."
        )
    return candidates[0]["uid"]


def _resolve(node, values, missing):
    """Substitute placeholders over a parsed document's leaf strings."""
    if isinstance(node, dict):
        return {key: _resolve(value, values, missing) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(item, values, missing) for item in node]
    if isinstance(node, str):
        missing.update(name for name in PLACEHOLDER.findall(node) if name not in values)
        return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), node)
    return node


def _load(alerting_dir, name, values):
    """Parse the committed file, THEN resolve its placeholders.

    Deliberately in that order. Substituting into the raw text first means a
    value carrying a YAML-significant character — a stray ``: ``, a leading
    brace, a quote — makes the parse fail, and PyYAML's error message quotes a
    window of the offending line. That window is the resolved Slack webhook URL,
    printed to stderr and kept forever in a CI log. Resolving into an already
    parsed structure cannot produce a parse error at all.
    """
    missing = set()
    document = _resolve(yaml.safe_load((alerting_dir / name).read_text()), values, missing)
    if missing:
        raise UnresolvedPlaceholder(
            f"{name}: no value supplied for "
            + ", ".join("$" + placeholder for placeholder in sorted(missing))
        )
    return document


def ensure_folder(stack):
    """The rules' own folder, so all three can be found — and removed — together."""
    if stack.find(f"/api/folders/{FOLDER_UID}") is None:
        stack.write("/api/folders", {"uid": FOLDER_UID, "title": FOLDER})
        return "created"
    return "present"


def apply_contact_point(stack, document):
    """Make the stack's contact point match the committed file exactly.

    Create, update, *and delete*: an integration dropped from the committed file
    has to disappear from the stack too. Without the delete, removing the email
    receiver here leaves the stack emailing the old address indefinitely with
    nothing in the repo left to explain why — and `apply_rules` next door
    promises the opposite behaviour, so the asymmetry would be invisible.

    Only integrations carrying this module's contact-point name are considered;
    another contact point's receivers are none of our business.
    """
    on_stack = {
        point.get("uid"): point
        for point in (stack.find("/api/v1/provisioning/contact-points") or [])
        if point.get("name") == CONTACT_POINT
    }
    applied, wanted = [], set()
    for point in document["contactPoints"]:
        for receiver in point["receivers"]:
            wanted.add(receiver["uid"])
            body = {"name": point["name"], **receiver}
            if receiver["uid"] in on_stack:
                stack.write(
                    f"/api/v1/provisioning/contact-points/{receiver['uid']}", body, method="PUT"
                )
                applied.append((receiver["type"], "updated"))
            else:
                stack.write("/api/v1/provisioning/contact-points", body)
                applied.append((receiver["type"], "created"))
    for uid in sorted(set(on_stack) - wanted):
        stack.delete(f"/api/v1/provisioning/contact-points/{uid}")
        applied.append((on_stack[uid].get("type", uid), "removed"))
    return applied


def apply_rules(stack, document):
    """Replace each committed rule group in one call.

    A group PUT rather than a POST per rule: it is idempotent by construction
    (re-running replaces rather than duplicating), it carries the evaluation
    interval, and a rule deleted from the committed file actually disappears
    from the stack instead of lingering as an orphan nobody remembers creating.

    Every group in the document, not just the first — a second group added to
    the builder would otherwise render, pass the drift check, and exist in git
    and nowhere else while provisioning reported success.
    """
    applied = {}
    for group in document["groups"]:
        rules = [
            {**rule, "folderUID": FOLDER_UID, "ruleGroup": group["name"]}
            for rule in group["rules"]
        ]
        stack.write(
            f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{group['name']}",
            {
                "title": group["name"],
                "folderUid": FOLDER_UID,
                "interval": _seconds(group.get("interval", EVAL_INTERVAL)),
                "rules": rules,
            },
            method="PUT",
        )
        applied.update({rule["uid"]: rule["title"] for rule in rules})
    return applied


def graft_route(stack, route):
    """Insert the fleet's route as the FIRST child of the stack's root policy.

    First, not last, and that ordering is the whole correctness of this
    function. Grafana walks a root's children in order and stops at the first
    match, with ``continue`` defaulting to false, so a stack carrying the
    ordinary "everything else goes here" catch-all child would swallow every
    fleet alert before it ever reached the fleet's route — Slack and email
    silent, provisioning reporting success.

    Replaces a previous fleet route rather than appending a second one. The
    match is on the receiver name as well as the matchers, because Grafana
    accepts and serves back more than one matcher encoding (``matchers`` as well
    as ``object_matchers``), and comparing only one of them leaves a stale twin
    ahead of the new route, where it wins every delivery.
    """
    tree = stack.find("/api/v1/provisioning/policies")
    if tree is None:
        # NOT an empty tree. A 404 here means the token lacks notification-policy
        # read scope, or the base URL has a path prefix — cases where writes may
        # still land. Synthesising a root from that would PUT the fleet's own
        # receiver over a root policy nobody ever read, sending every unmatched
        # alert on the stack to this Slack webhook and destroying the previous
        # root with no local copy of it. That is precisely the takeover this
        # module exists to avoid, so it is a hard stop.
        raise RuntimeError(
            "cannot read the stack's notification policy tree "
            "(/api/v1/provisioning/policies returned 404) — refusing to replace a root "
            "policy sight-unseen. Check that the token carries alerting/notification "
            "policy read scope and that GRAFANA_ALERTS_URL has no path prefix."
        )
    if not tree.get("receiver"):
        # A stack that genuinely has no root policy: ours becomes the root, with
        # the fleet route as its only child. Nothing is being displaced.
        tree = {"receiver": route["receiver"], "routes": []}
    children = tree.get("routes") or []
    others = [
        child for child in children
        if child.get("receiver") != route["receiver"]
        and child.get("object_matchers") != route["object_matchers"]
    ]
    replaced = len(others) != len(children)
    tree["routes"] = [route] + others
    stack.write("/api/v1/provisioning/policies", tree, method="PUT")
    return "replaced" if replaced else "added"


# Every health value Grafana reports for a rule it has actually run. A rule it
# has merely stored reads "unknown" (older builds default the field to "ok"),
# which is why health alone is not evidence — see confirm_rules.
EVALUATED_HEALTH = ("ok", "nodata", "error")

# Longer than EVAL_INTERVAL by a clear margin: a freshly written group's first
# tick is up to one whole interval away, so any deadline shorter than that would
# time out on every healthy provisioning run.
CONFIRM_DEADLINE_SECONDS = _seconds(EVAL_INTERVAL) * 2 + 120


def _evaluated_at(rule):
    """When Grafana last ran this rule, or None if it never has."""
    stamp = rule.get("lastEvaluation")
    if not stamp:
        return None
    try:
        when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    # Grafana zeroes the field rather than omitting it for a never-evaluated
    # rule, and year 1 is not a time anything ran.
    return None if when.year < 2000 else when


def confirm_rules(stack, rules, applied_at, deadline_seconds=CONFIRM_DEADLINE_SECONDS):
    """Prove the rules loaded AND that this stack has actually run them.

    Loading is not the same as working: Grafana accepts a rule whose datasource
    uid points at nothing, stores it, serves it back intact, and only reports
    `health: error` once evaluation runs. So the wait is for an *evaluation*,
    not for the rule to appear — and specifically for one stamped after the
    write this run performed. Two failures hide behind the weaker check:

    * A rule the stack has merely stored reports `health: "unknown"` (or, on
      older builds, `"ok"`) with a zeroed `lastEvaluation`, seconds after the
      PUT and long before the group's first tick. Accepting that reports success
      on rules pointing at a datasource that does not exist.
    * A *previous* run's `health: "error"` is still on record immediately after
      a corrected re-run's PUT, so trusting it fails the very run that fixed the
      problem, and tells the operator their fix did not take.

    ``rules`` maps uid → title; the title is the fallback identity for stacks
    whose ruler response omits the per-rule uid.
    """
    deadline = time.monotonic() + deadline_seconds
    while True:
        groups = (
            stack.get("/api/prometheus/grafana/api/v1/rules")
            .get("data", {})
            .get("groups", [])
        )
        by_identity = {}
        for group in groups:
            for rule in group.get("rules", []):
                for key in (rule.get("uid"), rule.get("name")):
                    if key:
                        by_identity[key] = rule
        fresh = {}
        for uid, title in rules.items():
            rule = by_identity.get(uid) or by_identity.get(title)
            when = _evaluated_at(rule) if rule else None
            if rule and when and when >= applied_at and rule.get("health") in EVALUATED_HEALTH:
                fresh[uid] = rule
        broken = {
            uid: rule.get("lastError") or "evaluation error"
            for uid, rule in fresh.items()
            if rule.get("health") == "error"
        }
        if broken:
            raise RuntimeError(
                "provisioned, but the stack cannot evaluate: "
                + "; ".join(f"{uid}: {error}" for uid, error in broken.items())
            )
        if len(fresh) == len(rules):
            return sorted(fresh)
        if time.monotonic() >= deadline:
            absent = [
                uid for uid, title in rules.items()
                if uid not in by_identity and title not in by_identity
            ]
            raise RuntimeError(
                f"{len(fresh)} of {len(rules)} rules had evaluated after {deadline_seconds}s"
                + (f"; never appeared: {', '.join(sorted(absent))}" if absent else "")
            )
        stack.sleep(5)


def provision(alerting_dir, base, token, values, echo=print, sleep=time.sleep,
              deadline_seconds=CONFIRM_DEADLINE_SECONDS):
    """Apply every committed artifact to the stack, then prove it evaluates."""
    stack = Stack(base, token, sleep=sleep)
    if not values.get("GRAFANA_METRICS_DATASOURCE_UID"):
        values = {**values, "GRAFANA_METRICS_DATASOURCE_UID": resolve_datasource_uid(stack)}
        echo(f"· datasource: discovered {values['GRAFANA_METRICS_DATASOURCE_UID']}")

    echo(f"· folder: {ensure_folder(stack)}")
    for kind, action in apply_contact_point(stack, _load(alerting_dir, CONTACT_POINTS_FILE, values)):
        echo(f"· contact point: {kind} {action}")
    # Stamped before the write, so an evaluation that merely *straddles* the PUT
    # can still count — and one recorded before it never can.
    applied_at = datetime.datetime.now(datetime.timezone.utc)
    rules = apply_rules(stack, _load(alerting_dir, RULES_FILE, values))
    echo(f"· rules: {len(rules)} applied")
    echo(f"· notification route: {graft_route(stack, _load(alerting_dir, POLICY_FILE, values)['route'])}")
    confirm_rules(stack, rules, applied_at, deadline_seconds=deadline_seconds)
    echo(f"✓ {len(rules)} rules provisioned and evaluating, delivering to the fleet-monitor contact point")
    return sorted(rules)
