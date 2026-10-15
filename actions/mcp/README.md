# govbot MCP

Ask Claude Desktop about your representatives, using government data cloned to your
own computer.

> **Who are my reps, and how do they align to my values?**

This is a thin adapter over the `govbot` command-line tool. It owns no database and
no data model — every answer comes from `govbot`, so anything Claude tells you can
be reproduced from a terminal in the same folder.

## What it does

1. Creates a **workspace** — a folder you own, holding your configuration and the
   data cloned so far. It is a git repository from the start, so you can publish it.
2. **Clones** legislation for the jurisdictions you care about, from public git
   repositories. No account, no API key, and no record of what you look up.
3. **Saves what you care about** as topic definitions in plain YAML you can edit.
4. **Tags** bills against those topics with an AI model that runs on your machine.
5. **Answers questions** with citations back to a repository, commit, and file path.

## Requirements

- Node 20+
- The `govbot` CLI:
  ```bash
  sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
  ```

## Install into Claude Desktop

Add this to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "govbot": {
      "command": "node",
      "args": ["/absolute/path/to/actions/mcp/dist/index.js"]
    }
  }
}
```

Then restart Claude Desktop and ask *"Who are my reps, and how do they align to my
values?"* — or pick the **who_are_my_reps** prompt.

### Configuration

| Variable | Meaning | Default |
|---|---|---|
| `GOVBOT_WORKSPACE` | Where the workspace folder lives | `~/govbot-workspace` |
| `GOVBOT_BIN` | Path to the `govbot` binary | `~/.govbot/bin/govbot`, else `PATH` |

## What it will not do

**It never asks for your address.** Finding out who represents you means a district
lookup, and doing that server-side would mean sending your home address to a
geocoder. Instead Claude asks who your representatives are and points you at
[openstates.org/find_your_legislator](https://openstates.org/find_your_legislator/)
or [congress.gov](https://www.congress.gov/members/find-your-member).

**It never invents a voting record.** Coverage is uneven and the tools say so:
Massachusetts publishes over eleven thousand bills and *zero* roll-call votes, and
Alaska publishes vote totals without recording how individuals voted. Every response
carries a coverage report, so "no results" is never confused with "your
representative did nothing".

**It does not guess between two people with the same surname.** govbot has no
legislator roster — sponsors and voters are names. Every match carries a confidence,
`--min-confidence` gates what can be attributed, and an ambiguous name returns the
candidates rather than a guess. Wyoming has two legislators named Brown; asking about
"Brown" attributes nothing and asks you which one you meant.

## Development

```bash
npm install
npm run build
npm test                # unit tests
./render-snapshots.sh   # regenerate __snapshots__/
```

Drive the server by hand:

```bash
node scripts/mcp-session.mjs __snapshots__/requests-surface.jsonl
```

That script also enforces the rule everything else depends on: **stdout carries
JSON-RPC frames and nothing else.** A stray `console.log` corrupts the transport and
Claude Desktop disconnects without an error message. All diagnostics go to stderr.

## Snapshots

`__snapshots__/surface.json` is the full tool, resource, and prompt surface. The
descriptions in it are shown to people when Claude asks permission to run something,
so changes to that wording are worth reviewing — the snapshot makes them a diff.

## Improvement loop

A Claude Code loop proposes improvements to this experience, builds the ones you
approve, and opens draft PRs with before/after screenshots from the real Claude
Desktop app. Its instructions are in `.claude/skills/mcp-improve/SKILL.md`, and the
scenarios it judges against are in `scenarios/`.

```
 /loop /mcp-improve
   │
   ├─ product-owner agent ── runs scenarios in Claude Desktop ──▶ issue (mcp-loop:proposal)
   │                                                                 │ you add mcp-loop:approved
   ├─ implementer agent ── worktree, tests, snapshots, bundle ──▶ draft PR
   │                                                                 │
   ├─ capture ── main vs PR build in Claude Desktop ──▶ before/after table in the PR
   │                                                                 │ you review / comment
   └─ implementer agent ── addresses comments, re-captures ◀────────┘   you merge
```

**One-time setup on the Mac that runs it:**

1. System Settings → Privacy & Security: give your terminal **Accessibility** and
   **Screen Recording** access.
2. `scripts/desktop-capture.sh setup`. This backs up `claude_desktop_config.json` and
   points its `govbot` entry at `~/.govbot/mcp-under-test`, where each install puts the server *and* a `govbot` CLI built from the same checkout, so PRs that change the Rust query code show it in their screenshots. It also points govbot at
   a separate workspace, `~/govbot-loop-workspace`, so scenarios never edit your own
   `govbot.yml`. Cloned data is shared with `~/govbot-workspace` through a symlink.
3. `scripts/desktop-capture.sh install --ref origin/main`. This builds `main` and
   restarts Claude Desktop on it.
4. In Claude Desktop, set govbot's tools to **Always allow**. Otherwise the
   permission prompt stops every automated run.
5. Clone the data the scenarios use: `cd ~/govbot-workspace && govbot clone il usa wy ma`.
6. `scripts/desktop-capture.sh doctor` should then report everything ok.

**Running it:** in Claude Code at the repo root, run `/loop /mcp-improve`, or
`/mcp-improve` for a single pass. It never takes over the keyboard while you are
using the Mac (5 minutes idle is the default), never merges, and never pushes to
`main`.

**Steering it from GitHub:**

- **Approve a proposal:** add `mcp-loop:approved` to the issue.
- **Reject a proposal:** close the issue as *not planned*.
- **Request changes:** comment on the PR. The loop addresses it on its next pass.

The capture camera also works on its own:
`scripts/desktop-capture.sh run scenarios/first-run.yml /tmp/captures`.
