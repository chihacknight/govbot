<!-- mcp-loop -->
<!-- mcp-loop:scenarios: SCENARIO_IDS_COMMA_SEPARATED -->

Closes #ISSUE

## What changes for the person using Claude Desktop

<!-- One or two sentences, in their terms. -->

## What changed in the code

<!-- Files and why; anything surprising. Keep it short — the diff is right below. -->

<!-- mcp-loop:captures:start -->
_Screenshots pending — captured on the next loop tick when this Mac is idle._
<!-- mcp-loop:captures:end -->

## Snapshot changes

<!-- "None", or what changed in __snapshots__/surface.json and why it is intended. -->

## Checks

| Check | Result |
|---|---|
| `npm run build && npm test` | <!-- ✅ N tests / ❌ output --> |
| `./render-snapshots.sh` | <!-- ✅ no diff / ✅ intended diff / ❌ --> |
| `scripts/build-bundle.sh` | <!-- ✅ / ❌ --> |

## Try it yourself

```bash
gh pr checkout PR_NUMBER
actions/mcp/scripts/desktop-capture.sh install .   # restarts Claude Desktop on this build
# then, in Claude Desktop: <the scenario prompt(s)>
actions/mcp/scripts/desktop-capture.sh install --ref origin/main   # back to main
```

---
Opened by the MCP improvement loop (`.claude/skills/mcp-improve`). Review comments
here are picked up on the next tick; merging is up to you.
