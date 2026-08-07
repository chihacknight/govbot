"""Apply the committed alerting artifacts to a real Grafana stack.

Grafana Cloud has no filesystem to drop provisioning files into, so the
committed YAML reaches a stack through the provisioning API. This module is that
path: read ``alerting/*.yaml``, resolve their placeholders, and PUT the result.

Two things here are deliberate and easy to get wrong:

* **The notification policy is replaced whole, never merged.** The stack is
  dedicated to the fleet monitor, so the committed tree IS the root. Grafana's
  policy API has no notion of a partial tree — a PUT to ``/policies`` swaps the
  whole root — and this module only issues that PUT over a tree it recognises:
  its own, or a fresh stack's untouched default. Anything else is a hard stop
  (see ``read_policy_tree``).
* **Every write carries ``X-Disable-Provenance``.** Without it Grafana marks
  API-provisioned resources read-only in the UI, and the first maintainer who
  tries to mute a rule or fix a webhook finds a greyed-out form and no
  explanation.
"""

import datetime
import json
import re
import time
import urllib.parse
import urllib.request

import yaml

from alerting import (CONTACT_POINT, CONTACT_POINTS_FILE, EVAL_INTERVAL, FOLDER,
                      FOLDER_UID, POLICY_FILE, RULES_FILE,
                      UnresolvedPlaceholder, PLACEHOLDER)
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

# The top-level key each committed document must carry, checked before the first
# write so a malformed one fails with a message rather than a KeyError halfway
# through a provisioning run.
REQUIRED_KEYS = {
    RULES_FILE: "groups",
    CONTACT_POINTS_FILE: "contactPoints",
    POLICY_FILE: "policies",
}

# Integrations this module created, and the only ones it will delete. Anything
# else on the fleet contact point was added by a maintainer through the UI — the
# editing that X-Disable-Provenance exists to allow — so pruning it would undo
# the very thing that header is for.
OWNED_UID_PREFIX = "fleet-monitor-"


def _seconds(duration) -> int:
    """A Grafana duration string as seconds; the rule-group API takes a number.

    Raises a `RuntimeError` naming the value rather than a `KeyError` or a
    `TypeError` from the middle of a parse: this runs after the folder and the
    contact points have already been written, so the failure a maintainer sees
    has to say which value was wrong, not print a traceback over a half-applied
    stack.
    """
    if isinstance(duration, bool) or (isinstance(duration, int) and duration <= 0):
        raise RuntimeError(f"{duration!r} is not a positive evaluation interval")
    if isinstance(duration, int):
        return duration
    match = DURATION.match(str(duration))
    if not match:
        raise RuntimeError(
            f"cannot read {duration!r} as an evaluation interval; "
            "use a plain number of seconds or <int>s / <int>m / <int>h"
        )
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2)]


def check_stack_url(base, name, allow_path=False) -> str:
    """A Grafana base URL this module is willing to talk to, trailing slash gone.

    Every request carries a bearer token and the contact-point body carries the
    resolved Slack webhook URL — itself a credential for posting to that
    channel — so plain http is refused. Three narrower refusals matter as much:

    * **Credentials in the URL.** `https://svc:GLSA_xxx@stack.grafana.net` is
      valid and would work, and every ``RequestFailed`` message embeds the URL
      it failed on. One 404 and the token is in the CI log, which is the one
      thing this module is otherwise careful to prevent.
    * **A query or fragment.** A base of `https://stack/?x` builds
      `https://stack/?x/api/folders` — the API path swallowed into a query
      string, so the request goes somewhere else entirely.
    * **A path prefix.** Every GET would 404, which `find()` reads as "not
      there yet" — a stack that looks empty and gets overwritten.
    """
    parsed = urllib.parse.urlparse(base)
    loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme == "http" and loopback:
        pass  # a local test stack; nothing leaves the machine
    elif parsed.scheme != "https":
        raise RuntimeError(
            f"{name} must be https (got {parsed.scheme or 'no scheme'}): a bearer token "
            "and the Slack webhook URL travel in these requests"
        )
    if parsed.username or parsed.password:
        raise RuntimeError(
            f"{name} carries credentials in the URL; put the token in "
            "GRAFANA_ALERTS_KEY instead — a failed request would print this URL"
        )
    if not parsed.hostname:
        raise RuntimeError(f"{name} has no host: {base!r}")
    try:
        parsed.port
    except ValueError:
        raise RuntimeError(f"{name} has an unreadable port: {base!r}") from None
    if parsed.query or parsed.fragment or parsed.params or base.endswith(("?", "#")):
        # `params` too: urlunparse would silently drop a `;p` segment, so the
        # deep link would point somewhere the operator did not configure.
        raise RuntimeError(
            f"{name} must be a bare origin: it carries a query, fragment, or path parameter"
        )
    if parsed.path.strip("/") and not allow_path:
        raise RuntimeError(
            f"{name} must be a bare origin: the path {parsed.path!r} would make every "
            "API request 404, which reads as an empty stack"
        )
    if parsed.scheme == "http" and urllib.request.getproxies().get("http") \
            and not urllib.request.proxy_bypass(parsed.netloc):
        # The loopback exemption assumes nothing leaves the machine, and urllib
        # has no implicit localhost proxy bypass — with http_proxy set, the token
        # and the webhook go to the proxy host in cleartext.
        raise RuntimeError(
            f"{name} is plain http and an http_proxy is configured; the bearer token would "
            "leave this machine in cleartext. Use https, or clear http_proxy."
        )
    path = parsed.path.rstrip("/") if allow_path else ""
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


class Stack:
    """The subset of Grafana's API this needs, over the shared retry helper."""

    def __init__(self, base, token, sleep=time.sleep):
        self.base = check_stack_url(base, "GRAFANA_ALERTS_URL")
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
    several provisions rules that evaluate against nothing, forever, while
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


def _segment(value, what) -> str:
    """A caller-supplied string safe to interpolate into an API path.

    Both the uid and the group name reach a URL, and both come from a YAML file
    ``--alerting-dir`` lets anyone point at. A uid of
    ``../../../../api/folders/x`` would send an authenticated write to a
    different endpoint entirely — urllib does not normalise dot segments on the
    client side, but Grafana's router does.
    """
    text = str(value)
    if "/" in text or ".." in text:
        raise RuntimeError(f"{what} {text!r} contains a path separator")
    return urllib.parse.quote(text, safe="")


def _resolve(node, values, missing):
    """Substitute placeholders over a parsed document's leaf strings.

    A placeholder present in ``values`` but empty counts as missing. Grafana
    accepts a contact point whose webhook URL is the empty string, then accepts
    alerts routed to it and drops them — an alerting setup that looks
    provisioned, reports healthy, and never reaches anyone. The CLI's credential
    gate already refuses an empty environment variable; this is the same refusal
    one layer down, for any other caller of ``provision()``.
    """
    if isinstance(node, dict):
        return {key: _resolve(value, values, missing) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve(item, values, missing) for item in node]
    if isinstance(node, str):
        missing.update(name for name in PLACEHOLDER.findall(node) if not values.get(name))
        return PLACEHOLDER.sub(
            lambda m: values[m.group(1)] if values.get(m.group(1)) else m.group(0), node
        )
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
    # Shape-checked here, before any write. `--alerting-dir` accepts any
    # directory, so a hand-edited or half-copied file is reachable — and a bare
    # KeyError from deep in `provision` is not a RuntimeError, so it escapes the
    # CLI's handler and prints a traceback over a half-applied stack.
    if not isinstance(document, dict) or REQUIRED_KEYS[name] not in document:
        raise RuntimeError(f"{name} is missing its top-level {REQUIRED_KEYS[name]!r} key")
    _check_shape(name, document)
    return document


def _fail(name, what):
    raise RuntimeError(f"{name}: {what}")


def _check_shape(name, document):
    """Validate every field the writers will index, not just the top-level key.

    Checking one key deep is not enough: `apply_rules` reaches `rule["uid"]` and
    `apply_contact_point` reaches `receiver["type"]`, and a bare KeyError from
    there is not a RuntimeError — it escapes the CLI's handler and prints a
    traceback over a stack that has already had its folder, contact point, and
    route written.
    """
    if name == RULES_FILE:
        groups = document["groups"]
        if not isinstance(groups, list) or not groups:
            _fail(name, "'groups' must be a non-empty list")
        for group in groups:
            if not isinstance(group, dict) or not group.get("name"):
                _fail(name, "every group needs a 'name'")
            rules = group.get("rules")
            if not isinstance(rules, list) or not rules:
                _fail(name, f"group {group['name']!r} has no rules")
            for rule in rules:
                if not isinstance(rule, dict) or not rule.get("uid") or not rule.get("title"):
                    _fail(name, f"every rule in {group['name']!r} needs a 'uid' and a 'title'")
    elif name == CONTACT_POINTS_FILE:
        points = document["contactPoints"]
        if not isinstance(points, list) or not points:
            _fail(name, "'contactPoints' must be a non-empty list")
        for point in points:
            if not isinstance(point, dict) or point.get("name") != CONTACT_POINT:
                # The reconcile pass only ever looks at receivers named
                # CONTACT_POINT, so a renamed document would create integrations
                # no run could later find — or clean up.
                _fail(name, f"every contact point must be named {CONTACT_POINT!r}")
            receivers = point.get("receivers")
            if not isinstance(receivers, list) or not receivers:
                _fail(name, "every contact point needs at least one receiver")
            for receiver in receivers:
                if not isinstance(receiver, dict) or not receiver.get("uid") \
                        or not receiver.get("type"):
                    _fail(name, "every receiver needs a 'uid' and a 'type'")
    else:
        policies = document["policies"]
        if not isinstance(policies, list) or len(policies) != 1 \
                or not isinstance(policies[0], dict):
            _fail(name, "'policies' must be a list of exactly one tree — a stack has one root")
        tree = policies[0]
        if tree.get("receiver") != CONTACT_POINT:
            _fail(name, f"the root receiver must be {CONTACT_POINT!r}")
        # The root matches every alert by construction, and Grafana silently
        # ignores matchers placed on it — so a file carrying them promises a
        # filter that does not exist, and provisioning it would "succeed".
        if tree.get("object_matchers") or tree.get("matchers"):
            _fail(name, "the root policy matches every alert; Grafana ignores matchers on it")
        # This module writes exactly one root and nothing under it. A child route
        # in the file means somebody is trying to route a stack that is supposed
        # to be dedicated — a design change, not a provisioning input.
        if tree.get("routes"):
            _fail(name, "the committed tree must have no child routes; the stack is dedicated "
                        "and the root delivers everything")


def ensure_folder(stack):
    """The rules' own folder, so they can be found — and removed — together."""
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
    points = stack.find("/api/v1/provisioning/contact-points") or []
    if not isinstance(points, list):
        raise RuntimeError(
            f"unexpected contact-points response from the stack ({type(points).__name__}); "
            "expected a list"
        )
    on_stack = {
        point["uid"]: point
        for point in points
        if isinstance(point, dict)
        # A uid is required, not assumed: a receiver returned without one would
        # otherwise key this dict under None and send a DELETE to `.../None` —
        # and mixing None with real uids makes the sort below raise instead.
        and point.get("name") == CONTACT_POINT and point.get("uid")
    }
    applied, wanted = [], set()
    for point in document["contactPoints"]:
        for receiver in point["receivers"]:
            wanted.add(receiver["uid"])
            body = {"name": point["name"], **receiver}
            if receiver["uid"] in on_stack:
                stack.write(
                    "/api/v1/provisioning/contact-points/"
                    + _segment(receiver["uid"], "contact-point uid"),
                    body,
                    method="PUT",
                )
                applied.append((receiver["type"], "updated"))
            else:
                stack.write("/api/v1/provisioning/contact-points", body)
                applied.append((receiver["type"], "created"))
    for uid in sorted(set(on_stack) - wanted):
        if not uid.startswith(OWNED_UID_PREFIX):
            # Added through the UI, which is exactly what X-Disable-Provenance
            # leaves open. Deleting it would make this command undo the editing
            # the provenance choice exists to permit.
            applied.append((on_stack[uid].get("type", uid), f"kept (not ours: {uid})"))
            continue
        stack.delete("/api/v1/provisioning/contact-points/" + _segment(uid, "contact-point uid"))
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
            f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/"
            + _segment(group["name"], "rule group name"),
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


# What a stack nobody has routed yet looks like: Grafana creates this receiver
# on every fresh instance, Cloud included, and the UI's "reset notification
# policy" restores it. The only tree this module will replace besides its own.
GRAFANA_DEFAULT_RECEIVER = "grafana-default-email"


def read_policy_tree(stack):
    """The stack's notification policy — ours or a fresh default, or a hard stop.

    Read BEFORE anything is written. The refusals below are only worth having if
    they happen before the rules land: a run that applies four enabled rules and
    then discovers the policy tree is not its to replace leaves them live and
    unrouted, so every fleet alert falls through to whatever receiver is there —
    and every retry reproduces it.

    This module owns the whole tree: the stack is dedicated to the fleet
    monitor, so the committed policy is the entire root and applying it is a
    plain PUT, no merging. What that ownership cannot survive is being pointed
    at a stack that is NOT dedicated — the PUT swaps the whole tree — so a root
    this module does not recognise is refused outright, never edited. (A merge
    path existed and was retired: inserting a route into a tree of unknown shape
    could not be made safe against arbitrary contents, and on a dedicated stack
    there is nothing to merge with.)
    """
    tree = stack.find("/api/v1/provisioning/policies")
    if tree is None:
        # NOT an empty tree. A 404 here means the token lacks notification-policy
        # read scope, or the base URL has a path prefix — cases where writes may
        # still land.
        raise RuntimeError(
            "cannot read the stack's notification policy tree "
            "(/api/v1/provisioning/policies returned 404) — refusing to replace a root "
            "policy sight-unseen. Check that the token carries alerting/notification "
            "policy read scope and that GRAFANA_ALERTS_URL has no path prefix."
        )
    # Recognisable as a policy tree, or we do not touch it. The rule is positive
    # on purpose: an earlier version refused only a tree with children and no
    # receiver, which let ANY other 200 body through as "genuinely empty" — a
    # proxy's {"status": "error"}, a maintenance page, a build that renamed the
    # field. Adopting one of those would PUT the fleet's own receiver over a
    # root nobody had read, with no copy of what was destroyed. Every real
    # Grafana ships a
    # default root receiver, so "neither key present" is far likelier to be a
    # body we don't recognise than a tree that is truly empty.
    if not isinstance(tree, dict) or not tree.get("receiver"):
        raise RuntimeError(
            "the stack's notification policy has no root receiver "
            f"(keys: {sorted(tree) if isinstance(tree, dict) else type(tree).__name__}). "
            "Refusing to overwrite it — every Grafana ships a default root receiver, so this "
            "is far likelier to be a response we don't recognise than a stack without one. "
            "Inspect /api/v1/provisioning/policies by hand."
        )
    children = tree.get("routes") or []
    if not isinstance(children, list) or any(not isinstance(c, dict) for c in children):
        # Checked here, before any write: the refusal message below names the
        # child receivers, and a string here would be walked character by
        # character, raising AttributeError — not a RuntimeError, so it escapes
        # the CLI's handler as a traceback.
        raise RuntimeError(
            "the stack's notification policy has a 'routes' value this module cannot read "
            f"({type(children).__name__}). Inspect /api/v1/provisioning/policies by hand."
        )
    if tree["receiver"] == CONTACT_POINT:
        # Ours — including one edited in the UI since, which apply_policy will
        # overwrite and say so.
        return tree
    if tree["receiver"] == GRAFANA_DEFAULT_RECEIVER and not children:
        # A fresh stack's untouched default. The default receiver WITH children
        # is not fresh — somebody routed this stack — and falls through.
        return tree
    named = ", ".join(sorted({str(child.get("receiver") or "?") for child in children}))
    raise RuntimeError(
        "the stack's notification policy is not this module's to replace: root receiver "
        f"{tree['receiver']!r}"
        + (f", child routes to {named}" if children else "")
        + ". provision-alerts writes the WHOLE tree of a stack dedicated to the fleet "
        "monitor. If this stack is dedicated, reset its notification policy to the default "
        "in the Grafana UI and re-run; if it is not, do not run this command against it."
    )


def apply_policy(stack, tree, desired):
    """Replace the stack's policy tree with the committed one — whole, not merged.

    ``tree`` is what ``read_policy_tree`` returned, and by then it is one of
    exactly two things: a fresh stack's default, or a tree this module wrote
    before — possibly edited in the UI since, which is the editing
    ``X-Disable-Provenance`` exists to allow. Either way the committed file
    wins. What matters is that resetting somebody's UI edit is SAID, not
    silent, so the operator learns the lasting place for the change is
    alerting.py.
    """
    stack.write("/api/v1/provisioning/policies", desired, method="PUT")
    if tree.get("receiver") != desired["receiver"]:
        return "adopted a fresh stack's default tree"
    # Keys the committed tree sets, plus the ways a UI edit can extend a policy
    # without touching any of them. Not every key Grafana serves back — the read
    # can carry server-added fields (a provenance stamp, a default it fills in)
    # that would report drift nobody created.
    watched = set(desired) | {"routes", "mute_time_intervals", "object_matchers", "matchers"}
    drift = sorted(
        key for key in watched
        if (tree.get(key) or None) != (desired.get(key) or None)
    )
    if drift:
        return "replaced, resetting UI edits to " + ", ".join(drift)
    return "replaced (no drift)"


# Every health value Grafana reports for a rule it has actually run. A rule it
# has merely stored reads "unknown" (older builds default the field to "ok"),
# which is why health alone is not evidence — see confirm_rules.
EVALUATED_HEALTH = ("ok", "nodata", "error")

# Longer than EVAL_INTERVAL by a clear margin: a freshly written group's first
# tick is up to one whole interval away, so any deadline shorter than that would
# time out on every healthy provisioning run.
CONFIRM_DEADLINE_SECONDS = _seconds(EVAL_INTERVAL) * 2 + 120

# A rule the pre-write ruler read did not list at all — distinct from one it
# listed as never evaluated. See evaluation_baseline.
NOT_LISTED = object()


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


def _rules_by_identity(stack):
    """The ruler API's rules, keyed by uid and by title.

    Both, because a stack whose response omits the per-rule uid can still be
    identified by title — and the fallback this replaced looked for
    ``__alert_rule_uid__`` in the rule's own labels, where Grafana never puts it
    (it is an alert *instance* label), so it could never have rescued anything.
    """
    groups = (
        stack.get("/api/prometheus/grafana/api/v1/rules").get("data", {}).get("groups", [])
    )
    seen, ambiguous = {}, set()
    for group in groups:
        # The title fallback is scoped to our own folder. Unscoped, a
        # maintainer-authored rule titled "Fleet data stale" in another folder —
        # a plausible name for someone watching the same fleet — would satisfy
        # confirmation for a rule of ours the stack never scheduled.
        # `folderUid` when the build provides it, else `file` — the namespace
        # field Grafana's Prometheus-compat API actually returns. NOT the group
        # `name`: ours is "fleet-monitor", never the folder title, so that arm
        # could only ever match somebody else's group.
        ours = group.get("folderUid") == FOLDER_UID or group.get("file") in (FOLDER, FOLDER_UID)
        for rule in group.get("rules", []):
            if rule.get("uid"):
                seen[rule["uid"]] = rule
            title = rule.get("name")
            if title and ours:
                # Two rules sharing a title are not an identity; last-wins would
                # silently pick one.
                if title in seen:
                    ambiguous.add(title)
                seen[title] = rule
    for title in ambiguous:
        del seen[title]
    return seen


def evaluation_baseline(stack, rules):
    """When the stack last evaluated each of these rules, before we write.

    The reference point for "has it run *our* rules yet", and it comes from the
    stack's own clock on purpose. Comparing Grafana's `lastEvaluation` against
    this host's wall clock needs a skew tolerance, and any tolerance wide enough
    to survive a laptop a few minutes fast is also wide enough to accept the
    evaluation that ran just *before* the write — which is the previous rule
    definitions, i.e. exactly the false pass this whole function exists to
    prevent. Two stamps from one clock need no tolerance at all.
    """
    seen = _rules_by_identity(stack)
    # The stack's own clock, read from the freshest evaluation anywhere on it.
    # Falling back to this host's clock for a rule the pre-write read didn't list
    # reintroduces exactly the cross-machine skew this baseline exists to avoid —
    # and NOT_LISTED is the normal state on a first-ever provisioning run, so
    # that fallback would be the common path, not the rare one.
    stamps = [when for rule in seen.values() if (when := _evaluated_at(rule))]
    latest = max(stamps) if stamps else None
    return latest, {
        # NOT_LISTED, not None: the ruler API transiently answers with no groups
        # at all while the scheduler reloads (a restart, a rule-group reload, a
        # Cloud rotation). Reading that as "never evaluated" would let the NEXT
        # poll accept a stamp left over from the previous, working definitions —
        # the same false pass this baseline exists to prevent, just through a
        # narrower window.
        uid: _evaluated_at(found) if (found := seen.get(uid) or seen.get(title)) else NOT_LISTED
        for uid, title in rules.items()
    }


def confirm_rules(stack, rules, baseline, stack_now=None,
                  deadline_seconds=CONFIRM_DEADLINE_SECONDS):
    """Prove the rules loaded AND that this stack has actually run them.

    Loading is not the same as working: Grafana accepts a rule whose datasource
    uid points at nothing, stores it, serves it back intact, and only reports
    `health: error` once evaluation runs. So the wait is for an *evaluation*,
    and specifically for one strictly newer than the ``baseline`` taken before
    the write. Two failures hide behind the weaker check:

    * A rule the stack has merely stored reports `health: "unknown"` (or, on
      older builds, `"ok"`) with a zeroed `lastEvaluation`, seconds after the
      PUT and long before the group's first tick. Accepting that reports success
      on rules pointing at a datasource that does not exist.
    * A *previous* run's `health: "error"` is still on record immediately after
      a corrected re-run's PUT, so trusting it fails the very run that fixed the
      problem, and tells the operator their fix did not take.

    ``rules`` maps uid → title; ``baseline`` maps uid → the evaluation time
    before this write, ``None`` for a rule the stack listed but had never run,
    and ``NOT_LISTED`` for one the pre-write read did not see at all.
    """
    deadline = time.monotonic() + deadline_seconds
    # The reference for a rule the pre-write read didn't list. The stack's own
    # freshest evaluation when there was one; this host's clock only when the
    # stack had nothing at all to compare against, where there is also nothing
    # stale to be fooled by.
    started = stack_now or datetime.datetime.now(datetime.timezone.utc)
    while True:
        by_identity = _rules_by_identity(stack)
        fresh = {}
        for uid, title in rules.items():
            rule = by_identity.get(uid) or by_identity.get(title)
            when = _evaluated_at(rule) if rule else None
            was = baseline.get(uid)
            if not (rule and when and rule.get("health") in EVALUATED_HEALTH):
                continue
            if was is NOT_LISTED:
                # The pre-write read didn't see this rule, so there is no stamp
                # to be newer than — and the reason might be a transient empty
                # ruler response rather than a genuinely new rule. Fall back to
                # this run's own start: a stamp older than that belongs to the
                # definitions we just replaced.
                if when > started:
                    fresh[uid] = rule
            elif was is None or when > was:
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
    echo(f"· applying {alerting_dir.resolve()}")

    # Every document is parsed, resolved, and shape-checked before the first
    # write, so a malformed file fails with a message instead of a KeyError over
    # a half-applied stack.
    if not values.get("GRAFANA_METRICS_DATASOURCE_UID"):
        values = {**values, "GRAFANA_METRICS_DATASOURCE_UID": resolve_datasource_uid(stack)}
        echo(f"· datasource: discovered {values['GRAFANA_METRICS_DATASOURCE_UID']}")
    contact_points = _load(alerting_dir, CONTACT_POINTS_FILE, values)
    document = _load(alerting_dir, RULES_FILE, values)
    # The file-provisioning wrapper's orgId stays out of the API body — the
    # policies endpoint takes the bare route object.
    policy = {
        key: value
        for key, value in _load(alerting_dir, POLICY_FILE, values)["policies"][0].items()
        if key != "orgId"
    }

    # Read the policy tree first: it is the only read that can refuse, and a
    # refusal after the rules land would leave them enabled and unrouted.
    tree = read_policy_tree(stack)

    echo(f"· folder: {ensure_folder(stack)}")
    # The contact point goes in before the policy: Grafana refuses a root
    # receiver that does not exist, so on a fresh stack the reverse order 400s.
    for kind, action in apply_contact_point(stack, contact_points):
        echo(f"· contact point: {kind} {action}")

    # The policy goes in BEFORE the rules. Ordering, not taste: the policy write
    # is the one that can still fail after the reads pass — Grafana 11 splits
    # `alert.rules:write` from `alert.notifications:write`, so a token holding
    # only the first gets through every check here and then 403s. With the rules
    # applied first that leaves them live and delivering to whatever receiver
    # was there, reproduced on every retry. Policy-first means a failure leaves
    # a tree routing alerts that do not exist yet, which is inert, and the rules
    # simply never land.
    echo(f"· notification policy: {apply_policy(stack, tree, policy)}")

    # Read the stack's current evaluation times before writing, so "has it run
    # our rules yet" is two stamps from one clock rather than a comparison
    # against this host's.
    wanted = {
        rule["uid"]: rule["title"] for group in document["groups"] for rule in group["rules"]
    }
    stack_now, baseline = evaluation_baseline(stack, wanted)
    rules = apply_rules(stack, document)
    echo(f"· rules: {len(rules)} applied")
    confirm_rules(stack, rules, baseline, stack_now=stack_now, deadline_seconds=deadline_seconds)
    echo(f"✓ {len(rules)} rules provisioned and evaluating, delivering to the fleet-monitor contact point")
    return sorted(rules)
