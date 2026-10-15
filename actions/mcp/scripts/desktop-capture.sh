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
#   MCP_CAPTURE_SIDEBAR     points cropped off the left, hiding chat history (default 250)
#   MCP_CAPTURE_COMPOSER    points at the bottom ignored when deciding "done" (default 180)
#   MCP_CAPTURE_MIN_WAIT    seconds before a reply can count as done (default 15)
#   MCP_CAPTURE_STABLE      seconds the reply must stay unchanged (default 10)
#   MCP_CAPTURE_PROMPT_PREFIX  text put before every scenario prompt, e.g. "Use govbot for this. "
#                           (with web search on, Claude Desktop often answers legislation
#                           questions from the web and never calls govbot; see the README)
#   MCP_CAPTURE_TIMEOUT     seconds before giving up on a reply (default 420)
#   MCP_CAPTURE_SIZE        "w,h" to resize the window first, e.g. "1280,1500" (default: leave as is;
#                           needs osascript itself in Accessibility, not just your terminal)
#   MCP_CAPTURE_ZOOM_OUT    ⌘− presses during a capture so more of the reply fits (default 2;
#                           reset with ⌘0 afterwards). Only needs keystroke access.
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
SIDEBAR="${MCP_CAPTURE_SIDEBAR:-250}"
COMPOSER="${MCP_CAPTURE_COMPOSER:-180}"
MIN_WAIT="${MCP_CAPTURE_MIN_WAIT:-15}"
STABLE="${MCP_CAPTURE_STABLE:-10}"
TIMEOUT="${MCP_CAPTURE_TIMEOUT:-420}"
ZOOM_OUT="${MCP_CAPTURE_ZOOM_OUT:-2}"
MAX_ALLOWS="${MCP_CAPTURE_MAX_ALLOWS:-8}"
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

ocr_bin() {
  local bin="$TARGET/bin/ocr"
  if [ ! -x "$bin" ] || [ "$HERE/ocr.swift" -nt "$bin" ]; then
    mkdir -p "$TARGET/bin"
    swiftc -O -o "$bin" "$HERE/ocr.swift" >&2 || die "could not compile ocr.swift"
  fi
  echo "$bin"
}

# Answer a tool-permission prompt with "Always allow" (⇧⌘⏎) ONLY when the prompt on
# screen is for one of govbot's own tools. Any other prompt (folder access, running
# commands, cloud uploads, other connectors) is left for a person: the capture
# times out and the screenshot shows the prompt, which is itself a finding.
allow_if_govbot_prompt() {
  local shot="$TARGET/capture-prompt.png" text
  require_claude_front
  rm -f "$shot"
  screencapture -x -R "$(content_rect)" "$shot"
  [ -s "$shot" ] || return 1
  text="$("$(ocr_bin)" "$shot" 2>/dev/null | tr '\n' ' ')"
  rm -f "$shot"
  case "$text" in
    *"wants to use"*" from "[Gg]"ovbot"*)
      case "$text" in *folder*|*command*|*"leave your device"*|*"U.S. Legislation"*) return 1 ;; esac
      osa 'tell application "System Events" to keystroke return using {command down, shift down}'
      say "[$id] allowed a govbot tool prompt"
      return 0 ;;
  esac
  return 1
}

# Typing goes to whatever app is frontmost, and screenshots capture whatever is on
# screen. Never do either unless Claude Desktop is the frontmost app.
require_claude_front() {
  local front
  front="$(osascript -e 'tell application "System Events" to get name of first process whose frontmost is true' 2>/dev/null)"
  [ "$front" = "Claude" ] || die "Claude Desktop is not the frontmost app (\"$front\" is); refusing to type or capture"
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
  check "a build is installed" "[ -f '$TARGET/server/dist/index.js' ] && [ -x '$TARGET/server/govbot' ]" "run: $0 install --ref origin/main"
  check "Rust toolchain (the CLI is built per capture)" "command -v cargo || [ -x '$HOME/.cargo/bin/cargo' ]" "install from rustup.rs"
  # Reading process names works without Accessibility; typing does not. "UI elements
  # enabled" is true only when this process may send keystrokes.
  check "Accessibility (can type into Claude Desktop)" \
    "[ \"\$(osascript -e 'tell application \"System Events\" to get UI elements enabled')\" = true ]" \
    "System Settings → Privacy & Security → Accessibility → add the app that runs this shell (and osascript if listed), then restart it"
  check "Screen Recording (can capture the screen)" \
    "screencapture -x -R 0,0,10,10 '$TARGET/capture-doctor.png' && [ -s '$TARGET/capture-doctor.png' ]" \
    "System Settings → Privacy & Security → Screen Recording → add your terminal; the screen must also be unlocked"
  check "window helper compiles" 'window_info_bin'
  check "loop workspace data at $WORKSPACE/govbot_data" "[ -d '$WORKSPACE/govbot_data' ]" "run: $0 setup"
  say "cloned: $(ls "$WORKSPACE/govbot_data/repos" 2>/dev/null | sed 's/-legislation//' | tr '\n' ' ')"
  say "idle for $(idle_seconds)s"
  [ -f "$TARGET/INSTALLED" ] && say "installed build: $(cat "$TARGET/INSTALLED")"
  rm -f "$TARGET/capture-doctor.png"
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
# The CLI is built from the same checkout as the server (see cmd_install), so a
# PR that changes `govbot query` shows that change in its captures.
env["GOVBOT_BIN"] = f"{target}/server/govbot"
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

  # Build the govbot CLI from the same checkout, in that checkout's own target
  # dir. A target dir shared between worktrees is NOT safe: cargo can judge a
  # binary built from another branch "fresh" and silently reuse it.
  local cargo="${CARGO:-$(command -v cargo || echo "$HOME/.cargo/bin/cargo")}"
  [ -x "$cargo" ] || die "cargo not found; the CLI must be built from $src/../govbot (install Rust: rustup.rs)"
  say "building the govbot CLI from $src/../govbot"
  (cd "$src/../govbot" && env -u CARGO_TARGET_DIR "$cargo" build --release --quiet --bin govbot) \
    || die "cargo build failed"
  cp "$src/../govbot/target/release/govbot" "$TARGET/server/govbot-real"
  # Desktop runs this shim, so a scenario can swap in a stub CLI (setup.env.GOVBOT_BIN)
  # without editing the Desktop config or restarting it.
  cat > "$TARGET/server/govbot" <<'SH'
#!/bin/sh
# Shim between the MCP server and the govbot CLI (installed by desktop-capture.sh).
# 1. A scenario can swap in a stub CLI by writing its path to bin-override.
# 2. Every call is appended to $GOVBOT_MCP_TRACE, so captures show exactly what the
#    server asked the CLI, whatever server build is installed (trace.ts only exists
#    on newer builds).
here="$(cd "$(dirname "$0")" && pwd)"
bin="$here/govbot-real"
[ -s "$here/bin-override" ] && bin="$(cat "$here/bin-override")"
[ -n "$GOVBOT_MCP_TRACE" ] || exec "$bin" "$@"
start="$(perl -MTime::HiRes=time -e 'printf "%d", time*1000')"
"$bin" "$@"
status=$?
end="$(perl -MTime::HiRes=time -e 'printf "%d", time*1000')"
python3 -c 'import json,os,sys,datetime
status, ms = int(sys.argv[1]), int(sys.argv[2])
args = sys.argv[3:]
rec = {"at": datetime.datetime.utcnow().isoformat() + "Z", "source": "cli",
       "tool": "govbot " + " ".join(a for a in args[:2] if not a.startswith("-")),
       "args": args, "ms": ms, "isError": status != 0}
open(os.environ["GOVBOT_MCP_TRACE"], "a").write(json.dumps(rec) + "\n")' \
  "$status" "$((end - start))" "$@" 2>/dev/null || true
exit $status
SH
  chmod +x "$TARGET/server/govbot"
  rm -f "$TARGET/server/bin-override"
  rev="$(git -C "$src" rev-parse --short HEAD) ($label)"
  echo "$rev from $src; cli sha $(shasum "$TARGET/server/govbot-real" | cut -c1-12)" > "$TARGET/INSTALLED"
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
  prompt="${MCP_CAPTURE_PROMPT_PREFIX:-}$(node "$HERE/read-scenario.mjs" "$scenario" prompt)"
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
  rm -f "$WORKSPACE/govbot.yml" "$WORKSPACE/README.md" "$WORKSPACE/.gitignore"
  if [ "$(node "$HERE/read-scenario.mjs" "$scenario" setup.workspace)" != fresh ]; then
    cp "$MCP_DIR/scenarios/workspace-baseline.yml" "$WORKSPACE/govbot.yml"
  fi
  # However the run ends, put the real CLI and the shared data folder back.
  trap 'rm -f "$TARGET/server/bin-override"; ln -sfn "$PERSONAL_DATA" "$WORKSPACE/govbot_data"' EXIT

  # Topic scores live in the workspace (country:us/…/tags). Clear them so one run's
  # tagging never changes what the next sees; setup.tags: personal copies the
  # person's real scores in instead, for scenarios about already-tagged data.
  rm -rf "$WORKSPACE/country:us"
  if [ "$(node "$HERE/read-scenario.mjs" "$scenario" setup.tags)" = personal ]; then
    [ -d "$HOME/govbot-workspace/country:us" ] || die "$scenario: setup.tags personal, but ~/govbot-workspace has no scores"
    cp -R "$HOME/govbot-workspace/country:us" "$WORKSPACE/"
  fi

  # setup.data: empty runs against an empty data folder (e.g. to watch a real
  # clone), then puts the shared data folder back and deletes what was cloned.
  local empty_data=""
  if [ "$(node "$HERE/read-scenario.mjs" "$scenario" setup.data)" = empty ]; then
    empty_data="$TARGET/empty-data"
    rm -rf "$empty_data"; mkdir -p "$empty_data"
    rm "$WORKSPACE/govbot_data"
    ln -s "$empty_data" "$WORKSPACE/govbot_data"
  fi

  # setup.workspace_files: {relative path: content} written after the reset, so a
  # scenario can start from a workspace the person has already edited.
  node -e '
    const [ws, json] = process.argv.slice(1);
    if (!json) process.exit(0);
    const fs = require("fs"), path = require("path");
    for (const [rel, text] of Object.entries(JSON.parse(json))) {
      const file = path.resolve(ws, rel);
      if (!file.startsWith(path.resolve(ws) + path.sep)) throw new Error("outside workspace: " + rel);
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, text);
    }' "$WORKSPACE" "$(node "$HERE/read-scenario.mjs" "$scenario" setup.workspace_files)"

  # setup.env: only GOVBOT_BIN is supported (via the shim from cmd_install); a path
  # is relative to the actions/mcp folder the scenario file lives in.
  local env_json bin_override=""
  env_json="$(node "$HERE/read-scenario.mjs" "$scenario" setup.env)"
  if [ -n "$env_json" ]; then
    bin_override="$(node -e '
      const env = JSON.parse(process.argv[1]);
      const extra = Object.keys(env).filter((k) => k !== "GOVBOT_BIN");
      if (extra.length) { console.error("unsupported setup.env keys: " + extra.join(", ")); process.exit(1); }
      process.stdout.write(env.GOVBOT_BIN ?? "");' "$env_json")" || die "$scenario: bad setup.env"
    if [ -n "$bin_override" ]; then
      bin_override="$(cd "$(dirname "$scenario")/.." && cd "$(dirname "$bin_override")" && pwd)/$(basename "$bin_override")"
      [ -x "$bin_override" ] || die "$scenario: GOVBOT_BIN $bin_override is not executable"
      [ -x "$TARGET/server/govbot" ] || die "reinstall first: this build has no CLI shim"
      echo "$bin_override" > "$TARGET/server/bin-override"
      say "[$id] using stub CLI $bin_override"
    fi
  fi

  : > "$TRACE"
  local clipboard; clipboard="$(pbpaste 2>/dev/null || true)"
  local started; started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  say "[$id] new chat, sending prompt"
  osa 'tell application "Claude" to activate'
  sleep 1
  require_claude_front
  osa 'tell application "System Events" to keystroke "n" using command down'
  sleep 2
  local i
  for ((i = 0; i < ZOOM_OUT; i++)); do osa 'tell application "System Events" to keystroke "-" using command down'; done
  printf '%s' "$prompt" | pbcopy
  require_claude_front
  osa 'tell application "System Events" to keystroke "v" using command down'
  sleep 1
  require_claude_front
  osa 'tell application "System Events" to key code 36'
  printf '%s' "$clipboard" | pbcopy

  # "Done" = the conversation area (window minus sidebar minus composer, where
  # the caret blinks) has not changed for $STABLE seconds. Tool calls in flight
  # show an animated indicator, so a long-running clone does not look finished.
  local rect x y w h probe last="" now stable=0 elapsed=0 timed_out=false allows=0 quiet=0 last_calls=""
  sleep "$MIN_WAIT"; elapsed=$MIN_WAIT
  # screencapture runs as its own process and may not be allowed to write into
  # sandboxed output folders, so capture under $TARGET and move the result.
  probe="$TARGET/capture-probe.png"
  while :; do
    rect="$(content_rect)"
    IFS=, read -r x y w h <<<"$rect"
    # screencapture can exit 0 without writing (e.g. a dot-prefixed file name),
    # so check the file, not the exit code.
    rm -f "$probe"
    require_claude_front
    screencapture -x -R "$x,$y,$w,$((h - COMPOSER))" "$probe"
    [ -s "$probe" ] || die "screencapture failed (Screen Recording permission? screen locked?)"
    now="$(md5 -q "$probe")"
    if [ "$now" = "$last" ]; then stable=$((stable + POLL)); else stable=0; last="$now"; fi
    if [ $stable -ge "$STABLE" ]; then
      # A reply that stops changing may be waiting on Desktop's tool-permission
      # prompt. ⇧⌘⏎ is its "Always allow" shortcut (setup step 4, by keyboard);
      # with no prompt showing it does nothing. If the screen changes, keep
      # waiting; if not, the reply really is finished.
      [ "$allows" -ge "$MAX_ALLOWS" ] && break
      allow_if_govbot_prompt || break
      allows=$((allows + 1))
      sleep 3; elapsed=$((elapsed + 3))
      stable=0; last=""
      continue
    fi
    # A permission prompt shows a pulsing dot, so the screen never looks finished.
    # If no CLI call has happened for a while, look for a govbot tool prompt.
    local calls; calls=$(wc -l < "$TRACE" | tr -d ' ')
    if [ "$calls" != "${last_calls:-}" ]; then last_calls=$calls; quiet=0; else quiet=$((quiet + POLL)); fi
    if [ "$quiet" -ge 20 ] && [ "$allows" -lt "$MAX_ALLOWS" ]; then
      allow_if_govbot_prompt && allows=$((allows + 1))
      quiet=0
    fi
    if [ $elapsed -ge "$TIMEOUT" ]; then timed_out=true; say "[$id] reply still changing after ${TIMEOUT}s; capturing anyway"; break; fi
    sleep $POLL; elapsed=$((elapsed + POLL))
  done
  rm -f "$probe"

  rm -f "$TARGET/capture-reply.png"
  require_claude_front
  screencapture -x -R "$(content_rect)" "$TARGET/capture-reply.png"
  [ -s "$TARGET/capture-reply.png" ] || die "screencapture wrote no image"
  mv "$TARGET/capture-reply.png" "$out/reply.png"
  [ "$ZOOM_OUT" -gt 0 ] && osa 'tell application "System Events" to keystroke "0" using command down' || true
  cp "$TRACE" "$out/trace.jsonl"
  if [ -n "$empty_data" ]; then
    rm "$WORKSPACE/govbot_data"
    ln -s "$PERSONAL_DATA" "$WORKSPACE/govbot_data"
    ls "$empty_data/repos" > "$out/cloned.txt" 2>/dev/null || true
    rm -rf "$empty_data"
  fi
  rm -f "$TARGET/server/bin-override"
  # What the workspace looked like afterwards, for expectations like "README.md
  # still contains …" (the data folder is a symlink and is left out).
  mkdir -p "$out/workspace"
  for f in govbot.yml README.md .gitignore; do
    [ -f "$WORKSPACE/$f" ] && cp "$WORKSPACE/$f" "$out/workspace/"
  done
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
