#!/usr/bin/env bash
# Publish screenshots to the `mcp-loop-assets` branch and print markdown for them.
#
#   publish-captures.sh <capture-dir> <dest-prefix>
#   e.g. publish-captures.sh /tmp/captures/after pr-142/after
#
# <capture-dir> is what desktop-capture.sh wrote: one folder per scenario, each with
# reply.png. Images live on an orphan branch so PRs can embed them without adding
# binaries to main's history. Prints one line per scenario:
#   <scenario-id>\t<raw image url>
set -euo pipefail

src="${1:?usage: publish-captures.sh <capture-dir> <dest-prefix>}"
prefix="${2:?usage: publish-captures.sh <capture-dir> <dest-prefix>}"
BRANCH=mcp-loop-assets
repo_root="$(git rev-parse --show-toplevel)"
assets="${MCP_LOOP_HOME:-$HOME/.govbot/mcp-loop}/assets"
slug="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

if [ ! -e "$assets/.git" ]; then
  mkdir -p "$(dirname "$assets")"
  if git -C "$repo_root" ls-remote --exit-code --heads origin "$BRANCH" >/dev/null; then
    git -C "$repo_root" fetch --quiet origin "$BRANCH"
    git -C "$repo_root" worktree add --quiet "$assets" "$BRANCH" 2>/dev/null \
      || git -C "$repo_root" worktree add --quiet -b "$BRANCH" "$assets" "origin/$BRANCH"
  else
    git -C "$repo_root" worktree add --quiet --detach "$assets"
    git -C "$assets" checkout --quiet --orphan "$BRANCH"
    git -C "$assets" rm -rf --quiet . >/dev/null 2>&1 || true
    printf '# mcp-loop assets\n\nScreenshots embedded in MCP improvement-loop PRs and issues. Not code.\n' > "$assets/README.md"
    git -C "$assets" add README.md
    git -C "$assets" commit --quiet -m "mcp-loop assets branch"
  fi
fi
git -C "$assets" pull --quiet --rebase origin "$BRANCH" 2>/dev/null || true

found=0
for shot in "$src"/*/reply.png; do
  [ -f "$shot" ] || continue
  id="$(basename "$(dirname "$shot")")"
  mkdir -p "$assets/$prefix"
  cp "$shot" "$assets/$prefix/$id.png"
  found=1
done
[ $found = 1 ] || { echo "no */reply.png under $src" >&2; exit 1; }

git -C "$assets" add "$prefix"
git -C "$assets" commit --quiet -m "captures: $prefix" || true
git -C "$assets" push --quiet origin "$BRANCH"
rev="$(git -C "$assets" rev-parse HEAD)"

# Pin URLs to the commit so a later re-capture never changes an old PR's images.
for shot in "$assets/$prefix"/*.png; do
  id="$(basename "$shot" .png)"
  printf '%s\thttps://raw.githubusercontent.com/%s/%s/%s/%s.png\n' "$id" "$slug" "$rev" "$prefix" "$id"
done
