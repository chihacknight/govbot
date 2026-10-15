---
name: mcp-improve
description: One tick of the self-improving loop for govbot's Claude Desktop (MCP) experience — address PR review feedback, attach Claude Desktop screenshots, build an approved proposal, or file new product proposals, whichever is first. Run repeatedly with `/loop /mcp-improve`.
---

# MCP improvement loop — one tick

Each invocation does **one** unit of work and stops. All state lives on GitHub
(labels, issues, PRs), so a tick is safe to repeat and you can steer it from your
phone:

| You do | Loop does next |
|---|---|
| Add `mcp-loop:approved` to a proposal issue | Builds it as a draft PR |
| Comment on / review a loop PR | Addresses it, pushes, re-captures |
| Close a proposal | Never proposes it again (it reads closed ones) |
| Merge a PR | Nothing — merging is always yours |

Paths below are relative to the repo root. Scripts live in
`.claude/skills/mcp-improve/scripts/`; call that `$S`.

## 0. Start

1. `cd "$(git rev-parse --show-toplevel)"`. Take the lock:
   `mkdir ~/.govbot/mcp-loop/lock 2>/dev/null` — if it exists and is younger than
   2 hours, another tick is running: report "busy" and stop. (Remove an older one.)
   **Remove the lock when the tick ends, however it ends.**
2. First run only (labels missing): create them —
   `gh label create mcp-loop -c 5319e7`, `mcp-loop:proposal -c c5def5`,
   `mcp-loop:approved -c 0e8a16`, `mcp-loop:in-progress -c fbca04`,
   `mcp-loop:needs-captures -c d4c5f9` (ignore "already exists").
3. `actions/mcp/scripts/desktop-capture.sh idle` — exit 75 means someone is at the
   Mac; pass `--busy` below and do nothing that drives Claude Desktop this tick.
4. `python3 $S/state.py [--busy]` → act on its `next` field, below.

When launching **mcp-implementer**, include this session's git commit and PR
attribution lines (from your system context) in its prompt so its commits and PRs
carry them.

## 1. `feedback` — a PR has review input newer than its last commit

For the first PR in `feedback`, launch the **mcp-implementer** agent with: the PR
number, branch, base, and the unresolved threads / comments / reviews from the state
JSON, and the instruction "address review feedback". It works in the PR's worktree,
pushes, and replies to each point. If its result says user-visible behaviour
changed, it adds `mcp-loop:needs-captures`.

## 2. `captures` — a PR is waiting for screenshots (only when not busy)

For the first PR in `needs_captures`:

1. Read the scenario ids from the PR body's `<!-- mcp-loop:scenarios: a,b -->` line.
2. `before=$($S/capture.sh base <ids>)`
3. `$S/capture.sh branch ~/.govbot/mcp-loop/worktrees/<branch> /tmp/mcp-loop/pr-<n>/after <ids>`
   (fetch and `git worktree add` it first if missing).
4. **Look at every PNG with Read before publishing.** If anything other than the
   govbot conversation is visible (other chat titles, notifications, personal
   content), do not publish it: comment on the PR that captures need the
   `MCP_CAPTURE_SIDEBAR` crop adjusted, and stop.
5. Judge each *after* capture against its scenario's `expect` using the screenshot and
   `trace.jsonl`. Write `{"<id>": "✅/⚠️/❌ one line"}` to a verdicts file. Be honest — a
   regression or a still-failing expectation is exactly what the reviewer needs to see.
6. `$S/publish-captures.sh <before> pr-<n>/before > b.tsv` (only the ids for this PR —
   copy them to a temp dir first), and the same for after → `a.tsv`.
7. `python3 $S/pr-captures.py --before <before> --after <after> --before-urls b.tsv
   --after-urls a.tsv --verdicts v.json --apply <n>`
8. `gh pr edit <n> --remove-label mcp-loop:needs-captures`.

If a capture fails (exit 1), still publish what succeeded and say which failed in the
verdicts. Never present a timed-out or failed capture as a pass.

## 3. `build` — an approved proposal has no PR yet

Take the oldest in `approved`. `gh issue edit <#> --add-label mcp-loop:in-progress`.
Launch the **mcp-implementer** agent with the issue number, base branch, and the
instruction "implement this proposal". It opens a draft PR labelled `mcp-loop` and
`mcp-loop:needs-captures`. If not busy, continue straight into step 2 for that PR in
the same tick, so the PR is reviewable as soon as you see it.

## 4. `propose` — fewer than 3 open proposals

1. If not busy: `before=$($S/capture.sh base)` (cached per base commit, so this is
   free after the first run on a commit). If busy, use the newest existing
   `~/.govbot/mcp-loop/captures/base-*` dir, or none.
2. Launch the **mcp-product-owner** agent with the capture dir (or "none"), how many
   proposals to file (3 minus open), and the base branch.
3. If it returns screenshots worth showing in an issue, publish them with
   `$S/publish-captures.sh <dir> proposal-<#>` and add them to the issue with
   `gh issue comment` (include the `<!-- mcp-loop -->` marker).

## 5. `idle`

Nothing to do. Say so in one line, and don't send a notification.

## End of every non-idle tick

- Remove the lock.
- Send a PushNotification of at most two lines naming what happened, with the
  issue or PR link, e.g. "Opened draft PR #231: structured results for query — 3
  scenarios captured".
- Every comment the loop writes on GitHub contains `<!-- mcp-loop -->`. That is how
  `state.py` tells your comments from the loop's, since both post as your account.

## Rules

- Never push to `main`, never merge, never force-push a branch you didn't create,
  never delete a branch. PRs are drafts; you mark them ready.
- Only one tick drives Claude Desktop at a time (the lock), and only when the Mac
  is idle.
- If a script fails in a way not covered here, stop and report it with its output
  rather than improvising a workaround — fail loudly.
