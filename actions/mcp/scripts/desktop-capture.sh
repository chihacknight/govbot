#!/usr/bin/env bash
# Drive the real Claude Desktop app through a scenario and screenshot the result.
#
# This is the camera for the MCP improvement loop (.claude/skills/mcp-improve). It
# installs a build of this server into one fixed place that Claude Desktop is
# pointed at, restarts Desktop so it loads that build, types a scenario's prompt
# into a new chat, waits for the reply to finish, and captures the window.
#
#   desktop-capture.sh doctor                    check permissions, config, data
#   desktop-capture.sh setup                     point Claude Desktop at the install target (once)
#   desktop-capture.sh install <dir> | --ref <git-ref>
#                                                build that checkout and restart Desktop on it
#   desktop-capture.sh run <scenario.yml> <outdir>
#                                                capture one scenario into <outdir>/<id>/
#   desktop-capture.sh idle                      exit 0 if the Mac is idle, 75 if someone is using it
#
# Exit codes: 0 ok, 1 failure, 2 usage, 75 deferred (someone is using the Mac).
#
# macOS only. The process running this needs Accessibility (to type into Desktop)
# and Screen Recording (to capture it) in System Settings → Privacy & Security.
#
# Tunables (environment):
#   GOVBOT_MCP_UNDER_TEST   install target            (default ~/.govbot/mcp-under-test)
#   MCP_LOOP_WORKSPACE      workspace the captured server uses (default ~/govbot-loop-workspace)
#   MCP_CAPTURE_IDLE_SECS   idle needed before typing (default 300)
#   MCP_CAPTURE_FORCE=1     skip the idle check (only when you are watching)
#   MCP_CAPTURE_SIDEBAR     points cropped off the left, hiding chat history (default 300)
#   MCP_CAPTURE_COMPOSER    points at the bottom ignored when deciding "done" (default 180)
#   MCP_CAPTURE_MIN_WAIT    seconds before a reply can count as done (default 15)
#   MCP_CAPTURE_STABLE      seconds the reply must stay unchanged (default 10)
#   MCP_CAPTURE_TIMEOUT     seconds before giving up on a reply (default 420)
#   MCP_CAPTURE_SIZE        "w,h" to resize the window first, e.g. "1280,1500" (default: leave as is)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MCP_DIR="$(cd "$HERE/.." && pwd)"

TARGET="${GOVBOT_MCP_UNDER_TEST:-$HOME/.govbot/mcp-under-test}"
CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
LOG="$HOME/Library/Logs/Claude/mcp-server-govbot.log"
TRACE="$TARGET/trace.jsonl"
# Scenarios run against their own workspace, reset before every run, so a
# scenario that saves values never touches the person's real govbot.yml. Its
# govbot_data links to the real workspace's, so public data is cloned only once.
WORKSPACE="${MCP_LOOP_WORKSPACE:-$HOME/govbot-loop-workspace}"
PERSONAL_DATA="$HOME/govbot-workspace/govbot_data"

IDLE_SECS="${MCP_CAPTURE_IDLE_SECS:-300}"
SIDEBAR="${MCP_CAPTURE_SIDEBAR:-300}"
COMPOSER="${MCP_CAPTURE_COMPOSER:-180}"
MIN_WAIT="${MCP_CAPTURE_MIN_WAIT:-15}"
STABLE="${MCP_CAPTURE_STABLE:-10}"
TIMEOUT="${MCP_CAPTURE_TIMEOUT:-420}"
POLL=2

say() { printf '[desktop-capture] %s\n' "$*" >&2; }
die() { say "error: $*"; exit 1; }

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

idle_seconds() {
  local ns
  ns="$(ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF; exit}')"
  echo $(( ${ns:-0} / 1000000000 ))
}

# Compile the window helper once; swiftc is part of the Xcode command line tools.
window_info_bin() {
  local bin="$TARGET/bin/window-info"
  if [ ! -x "$bin" ] || [ "$HERE/window-info.swift" -nt "$bin" ]; then
    mkdir -p "$TARGET/bin"
    swiftc -O -o "$bin" "$HERE/window-info.swift" >&2 || die "could not compile window-info.swift (xcode-select --install)"
  fi
  echo "$bin"
}

# Prints "x,y,w,h" of the Claude window in points, minus the sidebar.
content_rect() {
  local id x y w h
  read -r id x y w h < <("$(window_info_bin)" Claude) || die "Claude Desktop has no window on screen"
  echo "$((x + SIDEBAR)),$y,$((w - SIDEBAR)),$h"
}

ready_count() {
  [ -f "$LOG" ] || { echo 0; return; }
  grep -c 'govbot-mcp\] ready' "$LOG" || true
}

osa() { osascript -e "$@" >/dev/null; }

restart_desktop() {
  local before waited=0
  before="$(ready_count)"
  say "restarting Claude Desktop so it loads the new build"
  osa 'tell application "Claude" to quit' || true
  while pgrep -qf 'Claude.app/Contents/MacOS/Claude$' && [ $waited -lt 30 ]; do sleep 1; waited=$((waited + 1)); done
  open -a Claude
  waited=0
  while [ "$(ready_count)" -le "$before" ]; do
    [ $waited -ge 120 ] && die "govbot did not report ready within 120s; see $LOG"
    sleep 2; waited=$((waited + 2))
  done
  say "govbot is ready in Claude Desktop"
}

# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

cmd_idle() {
  local idle; idle="$(idle_seconds)"
  if [ "${MCP_CAPTURE_FORCE:-0}" = 1 ] || [ "$idle" -ge "$IDLE_SECS" ]; then
    say "idle for ${idle}s — ok to drive Claude Desktop"
    return 0
  fi
  say "someone used this Mac ${idle}s ago (< ${IDLE_SECS}s); deferring so we don't take over their keyboard"
  exit 75
}

cmd_doctor() {
  local ok=1
  check() { if eval "$2" >/dev/null 2>&1; then say "ok    $1"; else say "FAIL  $1${3:+ — $3}"; ok=0; fi; }
  check "Claude Desktop installed" '[ -d /Applications/Claude.app ]'
  check "Desktop config points govbot at $TARGET" \
    "python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); a=c[\"mcpServers\"][\"govbot\"][\"args\"][0]; sys.exit(0 if a.startswith(sys.argv[2]) else 1)' \"\$CONFIG\" \"\$TARGET\"" \
    "run: $0 setup"
  check "a build is installed" "[ -f '$TARGET/server/dist/index.js' ]" "run: $0 install --ref HEAD"
  check "Accessibility (can talk to System Events)" \
    "osascript -e 'tell application \"System Events\" to get name of first process'" \
    "System Settings → Privacy & Security → Accessibility → add your terminal"
  check "Screen Recording (can capture the screen)" \
    "screencapture -x -R 0,0,10,10 '$TARGET/.doctor.png'" \
    "System Settings → Privacy & Security → Screen Recording → add your terminal; the screen must also be unlocked"
  check "window helper compiles" 'window_info_bin'
  check "loop workspace data at $WORKSPACE/govbot_data" "[ -d '$WORKSPACE/govbot_data' ]" "run: $0 setup"
  say "cloned: $(ls "$WORKSPACE/govbot_data/repos" 2>/dev/null | sed 's/-legislation//' | tr '\n' ' ')"
  say "idle for $(idle_seconds)s"
  [ -f "$TARGET/INSTALLED" ] && say "installed build: $(cat "$TARGET/INSTALLED")"
  rm -f "$TARGET/.doctor.png"
  [ $ok = 1 ] || exit 1
}

cmd_setup() {
  [ -f "$CONFIG" ] || die "no Claude Desktop config at $CONFIG"
  local backup; backup="$CONFIG.bak-$(date +%Y%m%d%H%M%S)"
  cp "$CONFIG" "$backup"
  say "backed up config to $backup"
  python3 - "$CONFIG" "$TARGET" "$WORKSPACE" <<'PY'
import json, shutil, sys
config_path, target = sys.argv[1], sys.argv[2]
with open(config_path) as f:
    config = json.load(f)
servers = config.setdefault("mcpServers", {})
entry = servers.setdefault("govbot", {})
# Keep whatever node and env the person already had working; only repoint the
# server script and turn on the trace.
entry["command"] = entry.get("command") or shutil.which("node") or "node"
entry["args"] = [f"{target}/server/dist/index.js"]
env = entry.setdefault("env", {})
env["GOVBOT_MCP_TRACE"] = f"{target}/trace.jsonl"
env["GOVBOT_WORKSPACE"] = sys.argv[3]
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PY
  mkdir -p "$WORKSPACE" "$PERSONAL_DATA"
  [ -e "$WORKSPACE/govbot_data" ] || ln -s "$PERSONAL_DATA" "$WORKSPACE/govbot_data"
  say "govbot in Claude Desktop now runs from $TARGET/server against $WORKSPACE"
  say "(restart happens on next install; to undo, restore the backup above)"
}

cmd_install() {
  local src rev label
  if [ "${1:-}" = "--ref" ]; then
    label="$2"
    [ -n "${2:-}" ] || die "usage: install --ref <git-ref>"
    local repo; repo="$(git -C "$MCP_DIR" rev-parse --show-toplevel)"
    src="$TARGET/src"
    git -C "$repo" fetch --quiet origin || say "fetch failed; using local refs"
    if [ -d "$src/.git" ] || [ -f "$src/.git" ]; then
      git -C "$src" checkout --quiet --detach "$2"
    else
      mkdir -p "$TARGET"
      git -C "$repo" worktree add --quiet --detach "$src" "$2"
    fi
    src="$src/actions/mcp"
  else
    [ -n "${1:-}" ] || die "usage: install <checkout-or-actions/mcp-dir> | --ref <git-ref>"
    src="$(cd "$1" && pwd)"
    label="$(git -C "$src" rev-parse --abbrev-ref HEAD)"
    [ -f "$src/package.json" ] || src="$src/actions/mcp"
  fi
  [ -f "$src/package.json" ] || die "no actions/mcp under $1"

  say "building $src"
  (cd "$src" && npm ci --silent --no-audit --no-fund && npm run build --silent)
  mkdir -p "$TARGET/server"
  rsync -a --delete "$src/dist" "$src/node_modules" "$src/package.json" "$TARGET/server/"
  rev="$(git -C "$src" rev-parse --short HEAD) ($label)"
  echo "$rev from $src" > "$TARGET/INSTALLED"
  say "installed $rev"
  restart_desktop
}

cmd_run() {
  local scenario="${1:-}" outroot="${2:-}"
  [ -f "$scenario" ] && [ -n "$outroot" ] || die "usage: run <scenario.yml> <outdir>"
  [ -f "$TARGET/server/dist/index.js" ] || die "nothing installed; run: $0 install --ref HEAD"
  cmd_idle

  local id prompt out jurisdiction
  id="$(node "$HERE/read-scenario.mjs" "$scenario" id)"
  prompt="$(node "$HERE/read-scenario.mjs" "$scenario" prompt)"
  out="$outroot/$id"
  mkdir -p "$out"
  rm -f "$out"/*.png

  # Scenarios name the data they assume. Missing data is not a capture failure —
  # the scenario may be about exactly that — but it must be visible in the result.
  local missing=()
  while IFS= read -r jurisdiction; do
    [ -z "$jurisdiction" ] && continue
    [ -d "$WORKSPACE/govbot_data/repos/$jurisdiction-legislation" ] || missing+=("$jurisdiction")
  done < <(node "$HERE/read-scenario.mjs" "$scenario" setup.jurisdictions)
  [ ${#missing[@]} -gt 0 ] && say "warning: scenario expects ${missing[*]} cloned in $WORKSPACE"

  if [ -n "${MCP_CAPTURE_SIZE:-}" ]; then
    osa "tell application \"System Events\" to tell process \"Claude\" to set size of front window to {${MCP_CAPTURE_SIZE}}"
  fi

  # Reset the workspace so every capture starts from the same state.
  rm -f "$WORKSPACE/govbot.yml"
  if [ "$(node "$HERE/read-scenario.mjs" "$scenario" setup.workspace)" != fresh ]; then
    cp "$MCP_DIR/scenarios/workspace-baseline.yml" "$WORKSPACE/govbot.yml"
  fi

  : > "$TRACE"
  local clipboard; clipboard="$(pbpaste 2>/dev/null || true)"
  local started; started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  say "[$id] new chat, sending prompt"
  osa 'tell application "Claude" to activate'
  sleep 1
  osa 'tell application "System Events" to keystroke "n" using command down'
  sleep 2
  printf '%s' "$prompt" | pbcopy
  osa 'tell application "System Events" to keystroke "v" using command down'
  sleep 1
  osa 'tell application "System Events" to key code 36'
  printf '%s' "$clipboard" | pbcopy

  # "Done" = the conversation area (window minus sidebar minus composer, where
  # the caret blinks) has not changed for $STABLE seconds. Tool calls in flight
  # show an animated indicator, so a long-running clone does not look finished.
  local rect x y w h probe last="" now stable=0 elapsed=0 timed_out=false
  sleep "$MIN_WAIT"; elapsed=$MIN_WAIT
  probe="$out/.probe.png"
  while :; do
    rect="$(content_rect)"
    IFS=, read -r x y w h <<<"$rect"
    screencapture -x -R "$x,$y,$w,$((h - COMPOSER))" "$probe" || die "screencapture failed (Screen Recording permission? screen locked?)"
    now="$(md5 -q "$probe")"
    if [ "$now" = "$last" ]; then stable=$((stable + POLL)); else stable=0; last="$now"; fi
    [ $stable -ge "$STABLE" ] && break
    if [ $elapsed -ge "$TIMEOUT" ]; then timed_out=true; say "[$id] reply still changing after ${TIMEOUT}s; capturing anyway"; break; fi
    sleep $POLL; elapsed=$((elapsed + POLL))
  done
  rm -f "$probe"

  screencapture -x -R "$(content_rect)" "$out/reply.png"
  cp "$TRACE" "$out/trace.jsonl"
  python3 - "$out/meta.json" <<PY
import json, sys
json.dump({
    "scenario": "$id",
    "scenario_file": "$scenario",
    "build": open("$TARGET/INSTALLED").read().strip(),
    "started": "$started",
    "seconds": $elapsed,
    "timed_out": $( [ "$timed_out" = true ] && echo True || echo False ),
    "missing_data": $(printf '%s\n' "${missing[@]:-}" | python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().split() if l]))'),
    "tool_calls": sum(1 for _ in open("$out/trace.jsonl")),
}, open(sys.argv[1], "w"), indent=2)
PY
  say "[$id] captured $out/reply.png ($(wc -l < "$out/trace.jsonl" | tr -d ' ') tool calls, ${elapsed}s)"
  [ "$timed_out" = false ] || exit 1
}

case "${1:-}" in
  doctor) shift; cmd_doctor "$@" ;;
  setup) shift; cmd_setup "$@" ;;
  install) shift; cmd_install "$@" ;;
  run) shift; cmd_run "$@" ;;
  idle) shift; cmd_idle "$@" ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
