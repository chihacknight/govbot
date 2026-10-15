#!/usr/bin/env python3
"""Report what the MCP improvement loop should do next, as JSON.

Reads GitHub only (labels, issues, PRs, review threads) — the loop keeps no state of
its own, so it is safe to run any number of times and from any machine.

    python3 .claude/skills/mcp-improve/scripts/state.py [--busy]

--busy means someone is using this Mac (desktop-capture.sh idle exited 75), so
work that drives Claude Desktop is skipped this tick.

Output fields:
  base            branch loop PRs target (MCP_LOOP_BASE, default main)
  next            "feedback" | "captures" | "build" | "propose" | "idle" — the first that applies
  needs_captures  open loop PRs labelled mcp-loop:needs-captures
  feedback        open loop PRs with review input newer than their last commit
  approved        approved proposals with no open PR yet (oldest first)
  open_prs        all open loop PRs
  proposals       open proposals awaiting your decision
  wip_limit, proposal_target
"""

import json
import os
import subprocess
import sys

MARKER = "<!-- mcp-loop -->"  # on every comment the loop writes, to tell them apart from yours
WIP_LIMIT = int(os.environ.get("MCP_LOOP_WIP", "2"))
PROPOSAL_TARGET = int(os.environ.get("MCP_LOOP_PROPOSALS", "3"))


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def base_branch() -> str:
    return os.environ.get("MCP_LOOP_BASE", "main")


PR_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, first: 30, labels: ["mcp-loop"]) {
      nodes {
        number title url headRefName isDraft reviewDecision
        labels(first: 20) { nodes { name } }
        commits(last: 1) { nodes { commit { committedDate } } }
        reviewThreads(first: 100) {
          nodes { isResolved comments(first: 1) { nodes { body path line } } }
        }
        comments(last: 50) { nodes { body createdAt } }
        reviews(last: 30) { nodes { state body submittedAt } }
        closingIssuesReferences(first: 5) { nodes { number } }
      }
    }
  }
}
"""


def human(body: str) -> bool:
    return bool(body.strip()) and MARKER not in body


def main() -> None:
    owner, name = json.loads(gh("repo", "view", "--json", "nameWithOwner"))["nameWithOwner"].split("/")
    data = json.loads(gh("api", "graphql", "-f", f"query={PR_QUERY}", "-F", f"owner={owner}", "-F", f"name={name}"))
    prs = data["data"]["repository"]["pullRequests"]["nodes"]

    busy = "--busy" in sys.argv[1:]
    open_prs, feedback, needs_captures, linked = [], [], [], set()
    for pr in prs:
        last_commit = pr["commits"]["nodes"][0]["commit"]["committedDate"] if pr["commits"]["nodes"] else ""
        issues = [n["number"] for n in pr["closingIssuesReferences"]["nodes"]]
        linked.update(issues)
        unresolved = [
            t["comments"]["nodes"][0]
            for t in pr["reviewThreads"]["nodes"]
            if not t["isResolved"] and t["comments"]["nodes"] and human(t["comments"]["nodes"][0]["body"])
        ]
        new_comments = [c["body"] for c in pr["comments"]["nodes"] if c["createdAt"] > last_commit and human(c["body"])]
        new_reviews = [
            r["body"] or r["state"]
            for r in pr["reviews"]["nodes"]
            if r["submittedAt"] and r["submittedAt"] > last_commit and r["state"] in ("CHANGES_REQUESTED", "COMMENTED") and human(r["body"] or r["state"])
        ]
        entry = {"number": pr["number"], "title": pr["title"], "url": pr["url"], "branch": pr["headRefName"], "issues": issues}
        open_prs.append(entry)
        if "mcp-loop:needs-captures" in {l["name"] for l in pr["labels"]["nodes"]}:
            needs_captures.append(entry)
        if unresolved or new_comments or new_reviews:
            feedback.append({**entry, "unresolved_threads": unresolved, "new_comments": new_comments, "new_reviews": new_reviews})

    def issues(label: str) -> list:
        return json.loads(gh("issue", "list", "--state", "open", "--label", label, "--limit", "100",
                             "--json", "number,title,url,labels,createdAt"))

    approved = sorted(
        (i for i in issues("mcp-loop:approved") if i["number"] not in linked),
        key=lambda i: i["createdAt"],
    )
    proposals = [
        i for i in issues("mcp-loop:proposal")
        if not {l["name"] for l in i["labels"]} & {"mcp-loop:approved", "mcp-loop:in-progress"}
    ]

    if feedback:
        nxt = "feedback"
    elif needs_captures and not busy:
        nxt = "captures"
    elif approved and len(open_prs) < WIP_LIMIT:
        nxt = "build"
    elif len(proposals) < PROPOSAL_TARGET:
        nxt = "propose"
    else:
        nxt = "idle"

    slim = lambda items: [{k: i[k] for k in ("number", "title", "url")} for i in items]
    print(json.dumps({
        "base": base_branch(),
        "next": nxt,
        "busy": busy,
        "feedback": feedback,
        "needs_captures": needs_captures,
        "approved": slim(approved),
        "open_prs": open_prs,
        "proposals": slim(proposals),
        "wip_limit": WIP_LIMIT,
        "proposal_target": PROPOSAL_TARGET,
    }, indent=2))


if __name__ == "__main__":
    main()
