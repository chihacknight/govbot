# Folds consecutive INFO-level scrape log lines into collapsible GitHub Actions
# log groups (the same ::group::/::endgroup:: mechanism GitHub already uses for
# top-level steps), so a multi-hour scrape log collapses into a short, scannable
# list instead of one unbroken wall of text.
#
# Rule: fold a line if it looks like "HH:MM:SS INFO ..." (openstates/spatula's
# own log format, generic across every state -- not FL-specific). Everything
# else -- WARNING, ERROR, tracebacks (no per-line prefix at all), and scrape.sh's
# own status echoes -- stays exactly as printed, ungrouped and always visible.
# Deliberately an "INFO allowlist" rather than an "error blocklist": enumerating
# every error shape is exactly the fragile keyword-matching scrape.sh's own
# OTHER_ERRORS regex already struggles with; checking the log level instead is
# simpler and doesn't need to know what an error looks like.
#
# A group also breaks after MAX_CHUNK_SECONDS of continuous INFO output, so a
# long clean stretch doesn't become one enormous collapsed chunk.
#
# Deliberately only touches what's printed to stdout (the GitHub Actions log
# view) -- callers should tee the raw, ungrouped stream to the log file used
# for downstream parsing (bill counts, error detection) *before* piping through
# this filter, so nothing about that file's format changes.

BEGIN {
  in_group = 0
  chunk_start_epoch = -1
  MAX_CHUNK_SECONDS = 300
}

function close_group() {
  if (in_group) {
    print "::endgroup::"
    in_group = 0
  }
}

function open_group(label) {
  print "::group::  " label
  in_group = 1
}

{
  line = $0
  is_info = 0

  if (substr(line, 3, 1) == ":" && substr(line, 6, 1) == ":" && substr(line, 9, 5) == " INFO") {
    h = substr(line, 1, 2) + 0
    m = substr(line, 4, 2) + 0
    s = substr(line, 7, 2) + 0
    if (h ~ /^[0-9]+$/ && m ~ /^[0-9]+$/ && s ~ /^[0-9]+$/) {
      is_info = 1
      epoch = h * 3600 + m * 60 + s
    }
  }

  if (is_info) {
    if (!in_group) {
      open_group(substr(line, 1, 8) " onward")
      chunk_start_epoch = epoch
    } else if (epoch < chunk_start_epoch || epoch - chunk_start_epoch >= MAX_CHUNK_SECONDS) {
      close_group()
      open_group(substr(line, 1, 8) " onward")
      chunk_start_epoch = epoch
    }
    print line
  } else {
    close_group()
    print line
  }
}

END {
  close_group()
}
