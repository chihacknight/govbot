# Folds routine, high-volume scrape log lines into collapsible GitHub Actions
# log groups (the same ::group::/::endgroup:: mechanism GitHub already uses for
# top-level steps), so a multi-hour scrape log collapses into a short, scannable
# list instead of one unbroken wall of text.
#
# Two things get folded, both "INFO allowlist" style -- enumerating every error
# shape is exactly the fragile keyword-matching scrape.sh's own OTHER_ERRORS
# regex already struggles with, so instead this only folds lines it positively
# recognizes as routine, and leaves everything else exactly as printed:
#
# 1. Lines that look like "HH:MM:SS INFO ..." -- openstates/spatula's own log
#    format, generic across every state, not FL-specific.
# 2. Python's own `warnings.warn()` output (DeprecationWarning,
#    InsecureRequestWarning, etc.) -- a completely different code path than
#    `logging`, with no per-line prefix at all. Usually just two lines
#    ("/path/to/lib.py:1064: XWarning: message" then "  warnings.warn(...");
#    but if the warning's own message spans multiple lines (confirmed on a
#    real run -- google-auth's Python 3.9 EOL notice wraps across 3 lines),
#    everything up to the actual source-line continuation (always indented
#    with exactly two spaces, per Python's own default formatter) gets folded
#    too, capped at MAX_PYWARNING_BLOCK_LINES so unrecognized content can't
#    get stuck folding forever. This is generic library/runtime noise about
#    the codebase's own
#    housekeeping (deprecated APIs, disabled SSL verification, unsupported
#    Python version) repeated on every single request -- not a signal about
#    anything happening in the scrape itself, unlike openstates' own
#    logging-based WARNING/ERROR calls (self.logger.warning(...) etc. in
#    scraper code), which stay visible because they mean "this specific
#    bill/request had a real problem."
#
# WARNING, ERROR, tracebacks, and scrape.sh's own status echoes all fall
# through untouched, ungrouped, and always visible.
#
# A group also breaks after MAX_CHUNK_SECONDS of continuous foldable output,
# so a long clean stretch doesn't become one enormous collapsed chunk.
#
# Deliberately only touches what's printed to stdout (the GitHub Actions log
# view) -- callers should tee the raw, ungrouped stream to the log file used
# for downstream parsing (bill counts, error detection) *before* piping through
# this filter, so nothing about that file's format changes.

BEGIN {
  in_group = 0
  chunk_start_epoch = -1
  MAX_CHUNK_SECONDS = 300
  in_pywarning_block = 0
  pywarning_block_lines = 0
  MAX_PYWARNING_BLOCK_LINES = 20
  last_known_epoch = -1
  last_known_time = ""
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
  is_pywarning = 0

  if (in_pywarning_block) {
    is_pywarning = 1
    pywarning_block_lines++
    # Python's default warnings formatter always ends with the actual source
    # line, indented with exactly two spaces -- a multi-line message's own
    # wrapped text is whatever the message happens to use (commonly more than
    # two spaces, per google-auth's EOL notice), so this reliably distinguishes
    # "still inside the message body" from "this is the final line."
    if (line ~ /^  [^ ]/ || pywarning_block_lines >= MAX_PYWARNING_BLOCK_LINES) {
      in_pywarning_block = 0
    }
  } else if (line ~ /^\/[^ ]*:[0-9]+: [A-Za-z_]+Warning: /) {
    is_pywarning = 1
    in_pywarning_block = 1
    pywarning_block_lines = 0
  } else if (substr(line, 3, 1) == ":" && substr(line, 6, 1) == ":" && substr(line, 9, 5) == " INFO") {
    h = substr(line, 1, 2) + 0
    m = substr(line, 4, 2) + 0
    s = substr(line, 7, 2) + 0
    if (h ~ /^[0-9]+$/ && m ~ /^[0-9]+$/ && s ~ /^[0-9]+$/) {
      is_info = 1
      epoch = h * 3600 + m * 60 + s
      last_known_epoch = epoch
      last_known_time = substr(line, 1, 8)
    }
  }

  if (is_info) {
    if (!in_group) {
      open_group(last_known_time " onward")
      chunk_start_epoch = epoch
    } else if (epoch < chunk_start_epoch || epoch - chunk_start_epoch >= MAX_CHUNK_SECONDS) {
      close_group()
      open_group(last_known_time " onward")
      chunk_start_epoch = epoch
    }
    print line
  } else if (is_pywarning) {
    if (!in_group) {
      open_group((last_known_time != "") ? last_known_time " onward" : "warnings")
      if (last_known_epoch >= 0) {
        chunk_start_epoch = last_known_epoch
      }
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
