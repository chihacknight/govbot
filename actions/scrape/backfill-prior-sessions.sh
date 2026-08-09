#!/usr/bin/env bash
#
# backfill-prior-sessions.sh
#
# One-time (idempotent) backfill of INACTIVE / prior legislative sessions from
# the archived data org into the maintained one.
#
#   FROM:  govbot-archive/<state>-legislation   (renamed from chn-openstates-files;
#                                                 frozen, format workflows disabled,
#                                                 but still holds older sessions)
#   TO:    govbot-data/<state>-legislation      (the org `govbot clone` now reads;
#                                                 kept fresh by the daily pipeline,
#                                                 but only holds each state's ACTIVE
#                                                 session)
#
# Why: the scraper only produces the session OpenStates marks `active`, so when a
# state's repo was recreated under govbot-data it started with the current session
# only. Older sessions live on solely in the archive. This script copies just the
# session folders the archive has and govbot-data lacks -- so it NEVER touches the
# active session (which govbot-data keeps fresh) and can be re-run safely.
#
# Usage:
#   ./backfill-prior-sessions.sh nj              # one state
#   ./backfill-prior-sessions.sh nj co ar        # several
#   ./backfill-prior-sessions.sh all             # every jurisdiction govbot ships
#   DRY_RUN=1 ./backfill-prior-sessions.sh all   # show what WOULD be copied, no push
#
# Requirements:
#   * git + rsync
#   * `gh auth login` (or a git credential) with PUSH access to the govbot-data
#     repos. Run this from a machine/login that has that access -- the sandboxed
#     cloud sessions do not.
#
# Caveat on extracted text: repos may store PDF/XML-extracted text via Git LFS.
# This script clones with GIT_LFS_SKIP_SMUDGE=1 (the bill metadata + action logs,
# which are plain JSON, copy fine), so any LFS-backed extracted-text files are
# copied as pointer stubs, not real content. The core legislative data -- bills,
# sponsors, actions, votes -- is complete; re-run the extract action against the
# backfilled sessions later if you need their full text.

set -uo pipefail

ARCHIVE_ORG="govbot-archive"
DATA_ORG="govbot-data"
DRY_RUN="${DRY_RUN:-0}"

# Every jurisdiction code govbot ships (mirror of WorkingLocale; excludes the
# "all" keyword, which is not a repo). Update if the locale enum changes.
ALL_STATES="ak al ar ca co de fl ga gu hi ia id il in ks ky la ma md me mi mn mo \
mp ms mt nc nd ne nh nj nm nv ny oh ok or pa pr ri sc sd tn usa ut vi vt wa wi wv wy"

if [ "$#" -eq 0 ]; then
  echo "usage: $0 <state...|all>   (DRY_RUN=1 to preview)" >&2
  exit 1
fi
if [ "$1" = "all" ]; then STATES="$ALL_STATES"; else STATES="$*"; fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# List the session folder names in a repo's HEAD (one per line), or nothing.
list_sessions() { # <org> <state> <dir>
  local org="$1" st="$2" dir="$3"
  if ! git clone --filter=tree:0 --no-checkout --quiet \
        "https://github.com/$org/$st-legislation.git" "$dir" 2>/dev/null; then
    return 1
  fi
  git -C "$dir" ls-tree -d --name-only "HEAD:country:us/state:$st/sessions" 2>/dev/null | sort
}

overall=0
for st in $STATES; do
  echo "==== $st ===="
  sp="country:us/state:$st/sessions"

  data_sessions="$(list_sessions "$DATA_ORG" "$st" "$WORK/d_$st")" \
    || { echo "  skip: no $DATA_ORG/$st-legislation repo"; continue; }
  arch_sessions="$(list_sessions "$ARCHIVE_ORG" "$st" "$WORK/a_$st")" \
    || { echo "  skip: no $ARCHIVE_ORG/$st-legislation repo"; continue; }

  # Sessions to backfill = present in the archive, absent from govbot-data.
  # comm needs sorted input (list_sessions already sorts). Newline-delimited so
  # session names containing spaces (e.g. CA "... Special Session 1") survive.
  missing="$(comm -23 <(printf '%s\n' "$arch_sessions") <(printf '%s\n' "$data_sessions"))"
  missing="$(printf '%s\n' "$missing" | sed '/^$/d')"

  if [ -z "$missing" ]; then
    echo "  ✓ nothing to backfill (govbot-data already has: $(printf '%s ' $data_sessions))"
    continue
  fi
  echo "  will backfill:"; printf '      - %s\n' "$missing"
  if [ "$DRY_RUN" = "1" ]; then continue; fi

  # Full checkout of govbot-data (need a working tree to add + push).
  full="$WORK/full_$st"
  GIT_LFS_SKIP_SMUDGE=1 git clone --quiet \
      "https://github.com/$DATA_ORG/$st-legislation.git" "$full" \
    || { echo "  ✗ clone $DATA_ORG/$st failed"; overall=1; continue; }
  git -C "$full" config http.postBuffer 524288000   # some sessions are 10k+ files

  # Sparse-clone ONLY the missing session folders from the archive.
  arch="$WORK/arch_$st"
  GIT_LFS_SKIP_SMUDGE=1 git clone --quiet --filter=blob:none --sparse \
      "https://github.com/$ARCHIVE_ORG/$st-legislation.git" "$arch" \
    || { echo "  ✗ clone $ARCHIVE_ORG/$st failed"; overall=1; continue; }

  # Build the sparse path list (array to preserve spaces in session names).
  declare -a paths=()
  while IFS= read -r s; do [ -n "$s" ] && paths+=("$sp/$s"); done <<< "$missing"
  git -C "$arch" sparse-checkout set "${paths[@]}" 2>/dev/null

  # Copy each missing session folder across.
  copied=0
  while IFS= read -r s; do
    [ -n "$s" ] || continue
    src="$arch/$sp/$s"; dst="$full/$sp/$s"
    if [ ! -d "$src" ]; then echo "  ! session '$s' not materialized (LFS-only?), skipping"; continue; fi
    mkdir -p "$dst"; rsync -a "$src/" "$dst/"; copied=$((copied+1))
  done <<< "$missing"
  [ "$copied" -gt 0 ] || { echo "  ! nothing copied"; continue; }

  # Commit + push to govbot-data.
  git -C "$full" add "$sp"
  if git -C "$full" diff --staged --quiet; then
    echo "  ✓ already up to date after copy (no diff)"; continue
  fi
  msg="Backfill $copied prior session(s) from $ARCHIVE_ORG: $(printf '%s ' $missing)"
  git -C "$full" -c user.email="action@github.com" -c user.name="govbot backfill" \
      commit -q -m "$msg"
  if git -C "$full" push origin HEAD 2>&1 | tail -2; then
    echo "  ✅ pushed backfill for $st"
  else
    echo "  ❌ push failed for $st (need write access to $DATA_ORG/$st-legislation)"; overall=1
  fi
done

echo "backfill run complete."
exit "$overall"
