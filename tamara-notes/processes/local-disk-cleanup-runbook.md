# Local disk cleanup — self-hosted runners + Docker

Written 2026-08-05 after a real cleanup session that took 19Gi free → 33Gi free
on a 228Gi disk. Tamara runs more self-hosted `actions-runner-N` instances than
she actively dispatches jobs to, so idle ones silently accumulate Docker images,
containers, build cache, and stale `_work` checkouts. This doc is the repeatable
process, including the mistakes made along the way — read the "gotchas" section
before running anything destructive.

**Runner assignment**: `actions-runner-1` through `actions-runner-8` are the
scrapers (`govbot-openstates-scrapers/*`). `actions-runner-10` and
`actions-runner-20` are text extraction (`govbot-data/*`). Useful for guessing
which repo/workflow an idle runner's leftover `_work` checkout belongs to before
digging into `_PipelineMapping` — see Step 4.

## Quick triage: is anything actually running right now?

```bash
docker ps                      # live containers
ps aux | grep -i "scrape.sh\|docker run" | grep -v grep   # runner scripts mid-job
```

Don't assume `docker ps` alone tells the whole story — a runner job can be
between steps (e.g. still in `Checkout state repo`) with no container up yet.
Cross-check both.

## Step 1 — Docker cleanup (safe, reversible: everything re-pulls/rebuilds on demand)

```bash
docker system df                # see what's reclaimable before touching anything
docker container prune -f       # remove all *stopped* containers
docker image prune -a -f        # remove unused images (not referenced by a container)
docker builder prune -a -f      # clear build cache
```

This is low-risk — nothing here is unique data, it's all re-derivable (pull/build
again). In our session this alone reclaimed ~6.6GB (3.96GB images + 2.67GB cache).

**If a container is currently running a job you want to keep**: don't prune yet.
See Step 2 first — killing a live job needs to happen through GitHub, not `docker kill`.

**If `docker` commands fail with `failed to connect to the docker API` / `no such
file or directory`**: the daemon itself has died, usually because it ran out of
room. Check Docker Desktop's VM disk image directly — it does **not** shrink on
its own even after `docker system df` shows everything pruned, and can dwarf
every other number in this doc:
```bash
du -sh ~/Library/Containers/com.docker.docker/Data/vms/0/data/Docker.raw
```
Found this at **60GB** on 2026-08-07, the actual root cause of a 99%-full disk
that killed the laptop (everything else in this doc combined was single-digit
GB by comparison). If the daemon isn't running (`ps aux | grep -i docker` shows
only `com.docker.vmnetd`, no actual VM process), it's safe to delete the file
outright — Docker Desktop recreates an empty one on next launch, images
re-pull automatically. **Caveat**: this wipes any Docker *volumes* too, which
aren't auto-recreatable like images/containers are. Couldn't check for volumes
first since the dead daemon meant `docker volume ls` wasn't available either —
if that matters to you, try relaunching Docker Desktop briefly to check before
deleting.

## Step 2 — Killing an in-progress job the right way

If you need to stop a currently-running scrape/extract job, **don't just `docker
kill` or `kill` the local process.** That leaves the job stuck `in_progress` on
GitHub's side until it eventually times out (could be hours), and the runner
doesn't get properly freed.

1. Find the run: `gh run list --status in_progress --repo <owner>/<repo>` —
   **run this per state-repo**, not just the monorepo. Each state's scrape/extract
   job lives in its own repo (e.g. `govbot-openstates-scrapers/fl-legislation`,
   `govbot-data/ma-legislation`), so `gh run list` from inside `govbot/` will show
   nothing even when jobs are actively running locally.
2. Cancel it properly: `gh run cancel <run-id> --repo <owner>/<repo>`
3. *Then* kill the local container/process if it's still hanging around.
4. To restart: check the workflow supports `workflow_dispatch` (most of ours do —
   look for it in `.github/workflows/*.yml`), then
   `gh workflow run "<workflow name>" --repo <owner>/<repo>`.

**Mistake made this session**: killed local processes for 3 jobs assuming they
were orphaned leftovers (no `gh run list` hits in the `govbot` repo). Two of the
three turned out to be live runs in per-state repos, which then sat stuck
`in_progress` on GitHub until caught and cancelled properly. Always check the
actual state-repo before assuming a local process is an orphan.

## Step 3 — Finding bloated runner `_work` directories

Each `actions-runner-N/_work/<repo>/` is a live git checkout that persists
between jobs (that's by design — see "Why this happens" below). Idle runners
accumulate here.

```bash
du -sh /Users/tamara/actions-runner-*/_work 2>/dev/null | sort -rh
```

Watch for **nested runners** — one was found physically nested inside another
runner's directory (`actions-runner-20` inside `actions-runner-7`) after being
moved around manually. If a `du` total looks smaller than expected, check
`find <runner-dir> -maxdepth 3 -iname "*runner*"` for a stray nested copy before
concluding there's nothing to find.

For whichever directory looks oversized, break it down:

```bash
du -sh <runner>/_work/* | sort -rh          # which repo checkout is the hog
du -sh <checkout-path>/* | sort -rh          # which subfolder inside it
```

## Step 4 — Before deleting: verify it's actually redundant

**Do not delete a runner's `_work` checkout on file-age/size alone.** A stale
checkout can either be (a) genuinely superseded, safe to delete, or (b) the only
copy of real output from a run that failed *before* its commit/push step. Same
size and same staleness looked identical from the outside in both cases this
session — the only way to tell them apart was checking git state directly.

1. **Identify which repo it actually belongs to** — don't assume from the
   directory name alone (`ma-legislation` existed as *two different repos*,
   `govbot-openstates-scrapers/ma-legislation` and `govbot-data/ma-legislation`,
   with very different content and workflows):
   ```bash
   cd <checkout-path> && git remote -v
   ```
   Also check `<runner>/_work/_PipelineMapping/` — it names the exact org/repo
   the runner slot was assigned to.

2. **Check whether the working tree is even committed locally**:
   ```bash
   git status --short          # "??" = untracked, never staged, never committed here
   git rev-parse HEAD           # fails ("unknown revision") if branch is unborn
   ```
   `.git` being multiple GB does *not* mean "uncommitted work is safe in git" — it
   can just be fetched pack objects from `origin`, unrelated to what's sitting
   untracked in the working directory.

3. **The decisive check — diff the working tree against `origin/main` directly**,
   don't rely on "GitHub has a newer commit" as a proxy (that only proves *something*
   newer exists upstream, not that *this specific data* is included in it):
   ```bash
   git add -A                                    # stage everything, fully reversible, no commit
   git diff --cached origin/main --name-status > /tmp/diff.txt
   awk '{print $1}' /tmp/diff.txt | sort | uniq -c
   ```
   Read the status letters:
   - **`D` only, zero `A`/`M`** → everything in the local checkout already exists
     upstream, byte-identical. Fully redundant, safe to delete.
   - **Any `A`** → files that exist locally but not on `origin/main` — this is
     unique, unpushed work. Do not delete without investigating further (why didn't
     it push? does it need to be committed and pushed instead?).
   - **Any `M`** → local content differs from upstream — needs a real look, don't
     assume either version is safe to lose.

   This can be slow on a large tree (48k files took ~2+ min) — redirect to a file
   and give it a few minutes rather than assuming a timeout means it hung.

4. Only after `D`-only is confirmed: `rm -rf <runner>/_work` (or the specific repo
   checkout inside it). The runner will do a fresh `actions/checkout` next job.

## Step 4b — Recovering genuine unpushed work (when the diff shows `A`/`M`)

Happened for real on 2026-08-07: a `govbot-data/ma-legislation` checkout on
`actions-runner-20` (31GB) turned out to have 1,609 bills' worth of real
extraction output (`A`) plus 1,882 modified metadata files, on top of one local
commit that never made it to GitHub — almost certainly killed mid-run by the
same disk-full crash from Step 1's Docker note. This is recoverable, not lost:

1. **Commit whatever's staged from the Step 4 diff** (it's already `git add -A`'d):
   ```bash
   git commit -m "Recovered progress from interrupted run"
   ```
2. **Check it'll actually fast-forward** onto the *real* current `origin/main`
   (don't trust a stale local ref — confirm via API, since `git fetch` will
   likely fail per the auth gotcha below):
   ```bash
   gh api repos/<owner>/<repo>/commits/main --jq '.sha'   # compare to your cached origin/main
   git merge-base --is-ancestor origin/main HEAD && echo "clean fast-forward"
   ```
3. **Push it.** The runner's own `GITHUB_TOKEN` is long expired by the time you
   find this — expect `Invalid username or token. Password authentication is
   not supported for Git operations.` Two distinct causes produce that identical
   error, so check both:
   - **A leftover git config injected by `actions/checkout` overrides any
     credentials you pass.** Look for it:
     ```bash
     git config --local --list | grep includeif
     ```
     It points at a file like `_work/_temp/git-credentials-<uuid>.config`
     containing an `http.https://github.com/.extraheader` with the old expired
     token baked in as Basic auth — this silently wins over a fresh token
     embedded in your push URL. Fix: override it inline on every git command
     against this checkout:
     ```bash
     git -c http.https://github.com/.extraheader= push '<url-with-new-token>' HEAD:main
     ```
   - **If that's not it**, isolate token-vs-git-plumbing by testing the token
     against the API directly, bypassing git entirely:
     ```bash
     curl -sI -H "Authorization: token YOUR_TOKEN" https://api.github.com/repos/<owner>/<repo> | head -1
     ```
     `200` = token's fine, problem is git-side (the extraheader above, most
     likely). `401`/`403` = token itself is being rejected — check it's genuinely
     a classic PAT (not fine-grained, which needs the repo explicitly listed
     under "Repository access" and org approval) at
     https://github.com/settings/tokens, and that `repo` scope is checked.
   - Embed the token as `x-oauth-basic:<token>@github.com`, not `<token>@github.com`
     alone — the latter puts the token in the *username* slot and git will still
     stop to prompt for a password separately.
4. **If the push itself fails on a large commit** with `error: RPC failed; HTTP
   400` / `unexpected disconnect while reading sideband packet` after "Writing
   objects: 100%" — this hit at 556MB/8589 objects. Not a hard size-limit
   rejection (check first: `git ls-tree -r -l HEAD | awk '$4 > 100000000'` finds
   any single file over GitHub's 100MB hard cap, none did here). It's `git`'s
   default 1MiB `http.postBuffer` being too small plus HTTP/2 flakiness on very
   large single pushes. Fix — add both to the same push command as the
   extraheader override above:
   ```bash
   git -c http.https://github.com/.extraheader= -c http.postBuffer=1048576000 \
       -c http.version=HTTP/1.1 push '<url-with-new-token>' HEAD:main
   ```
   Worked cleanly on the retry. **After "Writing objects: 100%... done" prints,
   expect a long pause** — that's normal server-side repacking on GitHub's end
   for a push this size (took several minutes here), not a hang. Don't Ctrl+C;
   killing it there just reproduces the same failure and you start over. Confirm
   success by polling `gh api repos/<owner>/<repo>/commits/main --jq '.sha'`
   until it changes, rather than trusting the terminal looking idle.

   Result this session: 1,609 recovered bills, 447,871 line additions, landed
   as commit `0800ed061` on `govbot-data/ma-legislation` main — recovered
   cleanly, nothing lost.

**Token safety**: never paste a live token into a chat, ticket, or anywhere else
it'll be logged/persisted — if one does leak, treat it as compromised and delete
it immediately at https://github.com/settings/tokens before doing anything else,
then generate a fresh replacement. Happened this session; the exposed token was
revoked and rotated before use.

## Why this happens / how to prevent buildup

- `actions/checkout` (default settings, no `clean: false` override) runs `git
  clean -ffdx` + hard reset **every time a runner picks up a new job** — so
  checkouts self-clean automatically as long as a runner keeps getting reused.
- Buildup only happens when a runner **goes idle after a failed run** — e.g. a
  job fails, the runner never gets dispatched another job, and whatever was left
  in its working tree (partial output, downloaded PDFs, etc.) just sits there
  indefinitely since no subsequent checkout ever runs to wipe it.
- Given Tamara has more runners registered than she actively uses, idle ones are
  the norm, not the exception — worth periodically running Step 3's `du` sweep
  across *all* `actions-runner-*` directories, not just the ones currently in use.

## One-shot summary command

For a quick "how bad is it" read before doing a full pass:

```bash
df -h /
docker system df
du -sh /Users/tamara/actions-runner-*/_work 2>/dev/null | sort -rh
```
