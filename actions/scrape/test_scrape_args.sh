#!/usr/bin/env bash
# Offline test for scrape.sh's session / scrapers arguments (repo reorg steps 4 and 4b).
# A fake `docker` on PATH records each command, writes bill files into the mounted
# _data folder, and prints an os-update style report, so nothing touches the network.
# Needs bash, jq, awk, tar. Run: bash actions/scrape/test_scrape_args.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap '[ -n "${KEEP_TMP:-}" ] || rm -rf "$TMP"' EXIT; echo "tmp: $TMP"
fails=0

mkdir -p "$TMP/bin"
cat > "$TMP/bin/docker" <<'FAKE'
#!/usr/bin/env bash
# fake docker: `pull` succeeds; `run` logs its arguments after the image name.
[ "$1" = "pull" ] && exit 0
shift  # run
host_data=""; args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -v) [ -z "$host_data" ] && host_data="${2%%:*}"; shift 2 ;;
    --dns|-e) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
# args: image state scraper... ; drop the image
echo "${args[*]:1}" >> "$FAKE_DOCKER_LOG"
st="${args[1]}"
mkdir -p "$host_data/$st"
for i in 1 2 3; do echo "{\"identifier\": \"HB $i\"}" > "$host_data/$st/bill_$i.json"; done
# A stale block first (an earlier attempt's report), then the real one.
cat <<REPORT
$st (scrape)
bills scrape:
  duration:  0:00:01
  objects:
    bill: 100
    vote_event: 100
$st (scrape)
REPORT
has_votes=no
for a in "${args[@]:2}"; do [ "$a" = "votes" ] && has_votes=yes; done
echo "bills scrape:"
echo "  duration:  0:00:02"
echo "  objects:"
echo "    bill: 3"
echo "    vote_event: 2"
if [ "$has_votes" = yes ]; then
  echo "votes scrape:"
  echo "  duration:  0:00:01"
  echo "  objects:"
  echo "    vote_event: 5"
fi
exit 0
FAKE
chmod +x "$TMP/bin/docker"

run_case() {  # <name> <state> <session> <scrapers> -> sets RC, ARGS, SUMMARY
  local d="$TMP/$1"; mkdir -p "$d/work" "$d/out"
  export FAKE_DOCKER_LOG="$d/docker.log"; : > "$FAKE_DOCKER_LOG"
  PATH="$TMP/bin:$PATH" SCRAPE_AUTOSAVE_INTERVAL=100000 \
    bash "$HERE/scrape.sh" "$2" openstates/scrapers:latest "$d/work" "$d/out" '{}' main "$3" "$4" \
    > "$d/stdout.log" 2>&1
  RC=$?
  ARGS="$(cat "$FAKE_DOCKER_LOG")"
  SUMMARY="$d/out/scrape-summary.json"
}

expect() {  # <description> <actual> <expected>
  if [ "$2" = "$3" ]; then echo "  ✓ $1"; else echo "  ✗ $1: got [$2], want [$3]"; fails=$((fails + 1)); fi
}

echo "no session, no scrapers (today's behaviour)"
run_case default wy "" ""
expect "exit 0" "$RC" 0
expect "docker args" "$ARGS" "wy bills --scrape --fastmode"
expect "summary session" "$(jq -r .session "$SUMMARY")" ""
expect "summary scrapers" "$(jq -r .scrapers "$SUMMARY")" "bills"
expect "bill count from the last report block" "$(jq .objects.bill "$SUMMARY")" 3
expect "vote_event count" "$(jq .objects.vote_event "$SUMMARY")" 2
expect "warning history written (a clean log used to end the script first)" \
  "$(jq -r 'keys|length' "$TMP/default/out/.windycivi/warning_history.json" 2>/dev/null)" 1

echo "session + bills votes (TX 90R)"
run_case tx tx 90R "bills votes"
expect "exit 0" "$RC" 0
expect "session= after each scraper" "$ARGS" "tx bills session=90R votes session=90R --scrape --fastmode"
expect "summary session" "$(jq -r .session "$SUMMARY")" "90R"
expect "summary scrapers" "$(jq -r .scrapers "$SUMMARY")" "bills votes"
expect "bill count" "$(jq .objects.bill "$SUMMARY")" 3
expect "vote_events summed over both scrapers" "$(jq .objects.vote_event "$SUMMARY")" 7
expect "3 bill files saved" "$(find "$TMP/tx/out/_data/tx" -name 'bill_*.json' | wc -l | tr -d ' ')" 3

echo "session id with an underscore (GA 2025_26)"
run_case ga ga 2025_26 ""
expect "docker args" "$ARGS" "ga bills session=2025_26 --scrape --fastmode"

echo "NH keeps its no-fastmode rule"
run_case nh nh 2026 ""
expect "docker args" "$ARGS" "nh bills session=2026 --scrape"

echo "VA with no session: no special case any more (its old two-session repo has moved)"
run_case va-plain va "" ""
expect "docker args" "$ARGS" "va bills --scrape --fastmode"

echo "VA with a session and its csv_bills scraper (jurisdictions.yml)"
run_case va-2027 va 2027 "csv_bills"
expect "docker args" "$ARGS" "va csv_bills session=2027 --scrape --fastmode"

echo "unsafe values are refused before docker runs"
run_case bad-session tx '90R;rm -rf /' ""
expect "exit 1" "$RC" 1
expect "no docker run" "$ARGS" ""
run_case bad-scrapers tx 90R 'bills $(id)'
expect "exit 1" "$RC" 1
expect "no docker run" "$ARGS" ""

if [ "$fails" -eq 0 ]; then echo "OK"; else echo "FAILED: $fails"; exit 1; fi
