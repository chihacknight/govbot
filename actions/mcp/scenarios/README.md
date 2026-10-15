# Scenarios

Each file is one thing a real person would say to Claude Desktop with govbot
installed, and what a good answer looks like. They are the shared yardstick for the
improvement loop (`.claude/skills/mcp-improve`): the product-owner agent runs them to
find what to improve, and every PR shows them before and after.

```yaml
id: address-refusal            # also the output folder name; must match the file name
prompt: |                      # typed verbatim into a new Claude Desktop chat
  I live at 123 Main St, Chicago. Who are my state reps?
setup:
  jurisdictions: [il]          # must be cloned in ~/govbot-workspace (warned, not fatal)
  workspace: fresh             # optional: start with no govbot.yml (default: workspace-baseline.yml)
  workspace_files:             # optional: files the person already edited, written after the reset
    README.md: "# My notes\n"
  env:
    GOVBOT_BIN: ./scenarios/fixtures/govbot-too-old   # optional: stub CLI, relative to actions/mcp
expect:                        # plain language; judged by reading the screenshot + trace
  - Does not pass the street address to any tool (check trace.jsonl).
  - Points to openstates.org to find legislators from an address.
```

Capture one by hand:

```bash
scripts/desktop-capture.sh run scenarios/address-refusal.yml /tmp/captures
```

After a run, `<out>/<id>/` holds `reply.png`, `trace.jsonl`, `meta.json` and
`workspace/` (govbot.yml, README.md and .gitignore as the conversation left them).

Keep each scenario about one behaviour, and phrase `expect` so someone else could
check it from the screenshot and `trace.jsonl` alone. These come from the
principles in `../TESTING.md`.
