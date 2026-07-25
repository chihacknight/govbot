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

import json
import time

import yaml

from alerting import (CONTACT_POINTS_FILE, EVAL_INTERVAL, FOLDER, FOLDER_UID,
                      POLICY_FILE, RULES_FILE, substitute)
from http_util import RequestFailed, request_with_retry

# Editable in the UI after provisioning. The alternative is a maintainer meeting
# a locked form the first time they try to silence something.
PROVENANCE = {"X-Disable-Provenance": "true"}


def _seconds(duration: str) -> int:
    """A Grafana duration string as seconds; the rule-group API takes a number."""
    unit = duration[-1]
    return int(duration[:-1]) * {"s": 1, "m": 60, "h": 3600}[unit]


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


def _load(alerting_dir, name, values):
    return yaml.safe_load(substitute((alerting_dir / name).read_text(), values))


def ensure_folder(stack):
    """The rules' own folder, so all three can be found — and removed — together."""
    if stack.find(f"/api/folders/{FOLDER_UID}") is None:
        stack.write("/api/folders", {"uid": FOLDER_UID, "title": FOLDER})
        return "created"
    return "present"


def apply_contact_point(stack, document):
    """Create or update each integration, keyed by its stable uid."""
    existing = {
        point.get("uid") for point in (stack.find("/api/v1/provisioning/contact-points") or [])
    }
    applied = []
    for point in document["contactPoints"]:
        for receiver in point["receivers"]:
            body = {"name": point["name"], **receiver}
            if receiver["uid"] in existing:
                stack.write(
                    f"/api/v1/provisioning/contact-points/{receiver['uid']}", body, method="PUT"
                )
                applied.append((receiver["type"], "updated"))
            else:
                stack.write("/api/v1/provisioning/contact-points", body)
                applied.append((receiver["type"], "created"))
    return applied


def apply_rules(stack, document):
    """Replace the whole rule group in one call.

    A group PUT rather than three rule POSTs: it is idempotent by construction
    (re-running replaces rather than duplicating), it carries the evaluation
    interval, and a rule deleted from the committed file actually disappears
    from the stack instead of lingering as an orphan nobody remembers creating.
    """
    group = document["groups"][0]
    rules = [{**rule, "folderUID": FOLDER_UID, "ruleGroup": group["name"]} for rule in group["rules"]]
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
    return [rule["uid"] for rule in rules]


def graft_route(stack, route):
    """Insert the fleet's route under the stack's existing root policy.

    Replaces a previous fleet route rather than appending a second one — the
    match is on the route's own matchers, so re-running is idempotent and a
    stack ends up with exactly one branch belonging to this module.
    """
    tree = stack.find("/api/v1/provisioning/policies") or {}
    if not tree.get("receiver"):
        # A stack with no root policy at all: ours becomes the root, with the
        # fleet route as its only child. Nothing is being displaced here.
        tree = {"receiver": route["receiver"], "routes": []}
    others = [
        child for child in tree.get("routes") or []
        if child.get("object_matchers") != route["object_matchers"]
    ]
    replaced = len(others) != len(tree.get("routes") or [])
    tree["routes"] = others + [route]
    stack.write("/api/v1/provisioning/policies", tree, method="PUT")
    return "replaced" if replaced else "added"


def confirm_rules(stack, uids, deadline_seconds=120):
    """Prove the rules loaded AND that the stack can evaluate them.

    Loading is not the same as working: Grafana accepts a rule whose datasource
    uid points at nothing, stores it, serves it back intact, and only then
    reports `health: error` once evaluation runs. Waiting for that verdict is
    the difference between "the API took our JSON" and "these rules work".
    """
    deadline = time.monotonic() + deadline_seconds
    while True:
        groups = (
            stack.get("/api/prometheus/grafana/api/v1/rules")
            .get("data", {})
            .get("groups", [])
        )
        seen = {
            rule.get("uid") or rule.get("labels", {}).get("__alert_rule_uid__"): rule
            for group in groups
            for rule in group.get("rules", [])
        }
        broken = {
            uid: seen[uid].get("lastError") or "evaluation error"
            for uid in uids
            if uid in seen and seen[uid].get("health") == "error"
        }
        if broken:
            raise RuntimeError(
                "provisioned, but the stack cannot evaluate: "
                + "; ".join(f"{uid}: {error}" for uid, error in broken.items())
            )
        evaluated = [uid for uid in uids if uid in seen and seen[uid].get("health") not in (None, "")]
        if len(evaluated) == len(uids):
            return evaluated
        if time.monotonic() >= deadline:
            absent = [uid for uid in uids if uid not in seen]
            raise RuntimeError(
                f"{len(evaluated)} of {len(uids)} rules had evaluated after "
                f"{deadline_seconds}s"
                + (f"; never appeared: {', '.join(absent)}" if absent else "")
            )
        stack.sleep(5)


def provision(alerting_dir, base, token, values, echo=print, sleep=time.sleep,
              deadline_seconds=120):
    """Apply every committed artifact to the stack, then prove it evaluates."""
    stack = Stack(base, token, sleep=sleep)
    if not values.get("GRAFANA_METRICS_DATASOURCE_UID"):
        values = {**values, "GRAFANA_METRICS_DATASOURCE_UID": resolve_datasource_uid(stack)}
        echo(f"· datasource: discovered {values['GRAFANA_METRICS_DATASOURCE_UID']}")

    echo(f"· folder: {ensure_folder(stack)}")
    for kind, action in apply_contact_point(stack, _load(alerting_dir, CONTACT_POINTS_FILE, values)):
        echo(f"· contact point: {kind} {action}")
    uids = apply_rules(stack, _load(alerting_dir, RULES_FILE, values))
    echo(f"· rules: {len(uids)} applied")
    echo(f"· notification route: {graft_route(stack, _load(alerting_dir, POLICY_FILE, values)['route'])}")
    confirm_rules(stack, uids, deadline_seconds=deadline_seconds)
    echo(f"✓ {len(uids)} rules provisioned and evaluating, delivering to the fleet-monitor contact point")
    return uids
