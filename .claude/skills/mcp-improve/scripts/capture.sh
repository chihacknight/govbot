#!/usr/bin/env bash
# Capture scenario sets in Claude Desktop for the loop, on top of desktop-capture.sh.
#
#   capture.sh base [ids...]                 captures of origin/$MCP_LOOP_BASE (default main),
#                                            cached per commit; prints the capture dir
#   capture.sh branch <worktree> <out> ids...
#                                            captures of a PR worktree, then puts the
#                                            base build back so Desktop keeps working
#
# Scenario files are looked up in $MCP_LOOP_SCENARIOS (colon-separated dirs, e.g. a
# PR worktree's actions/mcp/scenarios first) and then this checkout's, so a scenario
# a PR adds can be captured against the base build too. With no ids, `base`
# captures every scenario in this checkout. Exits 75 (deferred) if someone is
# using the Mac, 1 if any capture failed — after capturing the rest.
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
desk="$repo/actions/mcp/scripts/desktop-capture.sh"
scenarios="$repo/actions/mcp/scenarios"
home="${MCP_LOOP_HOME:-$HOME/.govbot/mcp-loop}"
base="${MCP_LOOP_BASE:-main}"

all_ids() { for f in "$scenarios"/*.yml; do [ "$(basename "$f")" = workspace-baseline.yml ] || basename "$f" .yml; done; }

scenario_file() {
  local dir
  IFS=: read -ra dirs <<<"${MCP_LOOP_SCENARIOS:-}"
  for dir in "${dirs[@]}" "$scenarios"; do
    [ -n "$dir" ] && [ -f "$dir/$1.yml" ] && { echo "$dir/$1.yml"; return; }
  done
  return 1
}

run_ids() {  # <outdir> ids...
  local out="$1" failed=0; shift
  for id in "$@"; do
    file="$(scenario_file "$id")" || { echo "no scenario $id" >&2; failed=1; continue; }
    "$desk" run "$file" "$out" || { rc=$?; [ $rc = 75 ] && exit 75; failed=1; }
  done
  return $failed
}

"$desk" idle

case "${1:-}" in
  base)
    shift
    git -C "$repo" fetch --quiet origin "$base"
    sha="$(git -C "$repo" rev-parse --short "origin/$base")"
    out="$home/captures/base-$sha"
    ids=("$@"); [ ${#ids[@]} -gt 0 ] || ids=($(all_ids))
    missing=()
    for id in "${ids[@]}"; do [ -f "$out/$id/reply.png" ] || missing+=("$id"); done
    if [ ${#missing[@]} -gt 0 ]; then
      installed="$(cat "${GOVBOT_MCP_UNDER_TEST:-$HOME/.govbot/mcp-under-test}/INSTALLED" 2>/dev/null || true)"
      [[ "$installed" == "$sha "* ]] || "$desk" install --ref "origin/$base" >&2
      mkdir -p "$out"
      run_ids "$out" "${missing[@]}" >&2 || status=1
    fi
    echo "$out"
    exit "${status:-0}"
    ;;
  branch)
    worktree="${2:?usage: capture.sh branch <worktree> <out> ids...}"
    out="${3:?usage: capture.sh branch <worktree> <out> ids...}"
    shift 3
    [ $# -gt 0 ] || { echo "name at least one scenario" >&2; exit 2; }
    export MCP_LOOP_SCENARIOS="$worktree/actions/mcp/scenarios${MCP_LOOP_SCENARIOS:+:$MCP_LOOP_SCENARIOS}"
    "$desk" install "$worktree" >&2
    run_ids "$out" "$@" >&2 || status=1
    "$desk" install --ref "origin/$base" >&2
    echo "$out"
    exit "${status:-0}"
    ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
