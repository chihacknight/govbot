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
| `GOVBOT_NO_UPDATE_CHECK` | Set to `1` to never check for updates | unset |

## Updating

There are two pieces, and neither updates itself.

**The Claude Desktop extension (`govbot.mcpb`).** Claude Desktop only auto-updates
extensions installed from its own directory
([support article](https://support.claude.com/en/articles/10949351)). This one is
distributed privately, so updating is manual: download the latest bundle from

<https://github.com/chihacknight/govbot/releases/download/nightly/govbot.mcpb>

and drag it into Claude Desktop → Settings → Extensions. That URL always points at
the latest build from `main`. Submitting govbot to the extensions directory is the
eventual path to automatic updates.

**The `govbot` command-line tool.** Re-run the one-line installer; it replaces
`~/.govbot/bin/govbot` in place:

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

**How you find out.** At most once a day, in the background, the server fetches
[`govbot-mcp-version.json`](https://github.com/chihacknight/govbot/releases/download/nightly/govbot-mcp-version.json)
from the same release and caches it in `~/.govbot/update-check.json`. If a newer
extension exists, or the installed CLI is older than the server needs, a short
notice with the steps above appears in `setup_workspace` and `check_local_data`.
The check never delays an answer: offline, it gives up after 3 seconds in the
background and nothing is shown. Ask *"Is my govbot up to date?"* to see the
installed versions and the last check.

**Releasing.** `package.json`'s `version` is the source of truth; bump
`mcpb/manifest.json` with it (`scripts/build-bundle.sh` fails if they differ).
`govbot.cliMin` in `package.json` is the oldest CLI this server works with. The
nightly CLI reports the version in `actions/govbot/Cargo.toml`, so raising
`cliMin` only works together with a bump there.

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
