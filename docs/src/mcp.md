# Ask govbot from Claude Desktop

`actions/mcp` is a Claude Desktop server built on this data — for people who
would rather ask questions than run commands. It owns no database and no data
model: every answer comes from the `govbot` CLI against repositories cloned to
your own computer, so anything it tells you can be reproduced from a terminal
in the same folder.

## What you can do with it

- **Clone privately.** Download legislation for the jurisdictions you care
  about from public git repositories. No account, no API key, and no record
  of what you look up.
- **Ask without SQL.** Search bills, roll-call votes, and the people named in
  the data — e.g. *"Which Illinois bills mention rent control?"* or *"How did
  my representative vote on housing bills?"* Every result carries the
  repository, commit, and file path it came from.
- **Track what you care about.** Save topics in plain YAML, score bills
  against them with an AI model that runs on your machine, and start from the
  **who_are_my_reps** prompt to compare a voting record against your values.

## Install

Requirements: Node 20+ and the `govbot` CLI:

```bash
sh -c "$(curl -fsSL https://raw.githubusercontent.com/chihacknight/govbot/main/actions/govbot/scripts/install-nightly.sh)"
```

Add this to `claude_desktop_config.json` (Settings → Developer → Edit Config),
then restart Claude Desktop:

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

| Variable | Meaning | Default |
|---|---|---|
| `GOVBOT_WORKSPACE` | Where the workspace folder lives | `~/govbot-workspace` |
| `GOVBOT_BIN` | Path to the `govbot` binary | `~/.govbot/bin/govbot`, else `PATH` |

## What it will not do

- **It never asks for your address.** Placing you in a district would mean
  sending a home address to a geocoder, so instead it asks who your
  representatives are and points you at
  [openstates.org/find_your_legislator](https://openstates.org/find_your_legislator/)
  or [congress.gov](https://www.congress.gov/members/find-your-member).
- **It never invents a voting record.** Coverage is uneven and the answers say
  so: every response carries a coverage report, so "no results" is never
  confused with "your representative did nothing".
- **It does not guess between two people with the same surname.** Sponsors and
  voters are names, not roster entries — an ambiguous name returns the
  candidates rather than a guess.

Prefer reading from your phone with no install at all? The
[AI-assistant path](../../README.md#read-it-from-an-ai-assistant-no-install)
(`llms.txt` + `catalog.json`) covers that. For server development details, see
[`actions/mcp`](https://github.com/chihacknight/govbot/tree/main/actions/mcp).
