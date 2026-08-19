# Testing govbot in Claude Desktop

## It is already installed on this machine

`~/Library/Application Support/Claude/claude_desktop_config.json` now has a `govbot`
entry (the previous file was backed up alongside it). **Quit Claude Desktop
completely and reopen it** — it only reads that file at startup.

You should then see govbot under Settings → Developer, and a 🔌 icon in the chat
composer listing six tools.

Two details in that config are deliberate, and are the usual reasons a local MCP
server fails to start:

- `command` is the **absolute path** to node. Claude Desktop launches servers with a
  minimal environment, and a bare `node` is not found.
- `env.PATH` is set so the server can find `git`, which `govbot clone` needs.

## Try this first

> **Who are my reps, and how do they align to my values?**

Illinois and Congress are already cloned (`~/govbot-workspace/govbot_data`), and the
local tagging model is already downloaded, so you should not have to wait.

You can also pick **who_are_my_reps** from the prompt picker (the `+` in the
composer) instead of typing.

## Worth checking specifically

These are the behaviours that matter more than the happy path.

**1. It should never ask for your address.** Say *"I live at 123 Main St, Chicago"*
and watch what it does. It should decline to use that and point you at
openstates.org instead. Verify nothing sent it onward:

```bash
grep -ri "123 Main" ~/Library/Logs/Claude/mcp-server-govbot.log
```

**2. It should refuse to guess between two people with the same name.** Ask about a
Wyoming legislator named **Brown** (clone Wyoming first: *"clone Wyoming"*). There
are two. It should name both and ask which you meant, not pick one.

**3. It should say when data does not exist, rather than implying inaction.** Clone
Massachusetts and ask how one of your state representatives voted on something.
Massachusetts publishes 11,287 bills and **zero** roll-call votes. The honest answer
is "that state does not publish this", not "no votes found".

**4. Every claim should carry a citation.** Ask it to show you where a claim came
from. You should get a repository, a commit, and a path — check one:

```bash
cat ~/govbot-workspace/govbot_data/repos/il-legislation/country:us/state:il/sessions/104th/bills/SB3763/metadata.json
```

**5. The workspace should be yours.** Open `~/govbot-workspace/govbot.yml` after you
have told it what you care about. It should describe your values in plain YAML you
can edit. Change something and ask it to re-tag.

## Running the same queries yourself

Everything Claude does is reproducible from a terminal:

```bash
cd ~/govbot-workspace
~/.govbot/bin/govbot query coverage
~/.govbot/bin/govbot query bills --jurisdiction il --text "rent" --limit 10
~/.govbot/bin/govbot query votes --jurisdiction il --person "Cunningham, Bill" --limit 5
~/.govbot/bin/govbot logs | ~/.govbot/bin/govbot tag --overwrite
```

## If it does not start

```bash
tail -50 ~/Library/Logs/Claude/mcp-server-govbot.log
```

The server prints a `ready` line on startup. If you see nothing, the launch failed
before that — usually node or the config path.

## Testing the bundle instead

`govbot.mcpb` (3.2 MB) is the one-file install a non-technical person would use.
To test that path, first **remove the `govbot` entry from
claude_desktop_config.json** so you are not running two copies, then open the
bundle. It is unsigned, so macOS will warn.
