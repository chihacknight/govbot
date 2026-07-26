---
name: fl-single-bill-failure-handoff
description: Handoff doc -- why one bill's network failure crashes the entire remaining FL scrape session, with a likely root cause already traced from tonight's traceback. Start here in a fresh chat.
metadata:
  type: project
---

# FL: one bill's failure kills the whole remaining session

## Context (read this first)

Tonight (2026-07-23/24) we found and fixed two real bugs in FL's scraper, both in
PR [#5724](https://github.com/openstates/openstates-scrapers/pull/5724) (branch
`fix/fl-streaming-bills` in `~/tad_code.nosync/current/openstates-scrapers`):

1. The `list()` anti-pattern -- bills were held in memory and never written to disk until the
   *entire* ~1,900-bill session finished. Fixed by streaming (`yield from` instead of `list(...)`).
2. Missing `timeout=` on the three `flhouse.gov` request constructions in `fl/bills.py`
   (`HouseSearchPage`/`HouseBillPage`) -- a stalled connection would hang forever with no
   timeout to ever trigger the existing retry logic. Fixed with `timeout=10`.

Both fixes are confirmed working: a self-hosted run tonight landed **413 real bills** committed
to `govbot-openstates-scrapers/fl-legislation` -- the first real FL data since 2026-07-02.

**This doc is about a third, separate, not-yet-fixed issue**, found in that same successful run's
final failure: when a single bill's request to `flhouse.gov` fails (even after exhausting its own
3 retries), it crashes the *entire remaining scrape*, rather than logging that one bill as failed
and continuing to the next one. Given there are ~1,900 bills and any single one of them can hit a
transient network blip, this means the run's ultimate success is still needlessly fragile --
one bad bill near the end can cost you everything after that point, even though every other bill
is completely independent of it.

## The evidence (from tonight's real run)

Bill HB/SB 66's `HouseSearchPage` fetch failed:

```
13:30:18 WARNING root: Connection error when fetching https://flhouse.gov/Sections/Bills/bills.aspx?...BillNumber=66: Read timed out. (read timeout=10)
... [3 retries, backoff 4s/9s/21s, user-agent rotated each time] ...
13:31:27 ERROR fl.utils: Max retries (3) exceeded. Last error: ReadTimeout
```

Full traceback (the key part, from `scrapelib`/`requests` up through `spatula`):

```
File "spatula/pages.py", line 229, in _to_items
    yield from item._to_items(scraper)
File "spatula/pages.py", line 229, in _to_items
    yield from item._to_items(scraper)
File "spatula/pages.py", line 209, in _to_items
    self._fetch_data(scraper)
File "spatula/pages.py", line 172, in _fetch_data
    response = self.source.get_response(scraper)
...
File "scrapers/fl/bills.py", line 85, in patched_get_response
    return retry_on_connection_error(...)
...
requests.exceptions.ReadTimeout: ...
⚠️ scrape attempt 3 failed; sleeping 20s...
Found 149 JSON files in _working/_data/fl
⚠️ Scrape failed (exit code 1) despite 149 partial JSON file(s) on disk; discarding partial output
```

That last line matters: 149 files scraped since the last auto-save (30-min cadence) were
discarded because the overall docker process exited non-zero. This was also the *last* of
`scrape.sh`'s own 3 outer container-level retry attempts, so nothing auto-restarted afterward.
(Everything auto-saved *before* this point is safe and already committed -- this is only about
the newest ~149 files at the moment of the crash.)

## Likely root cause (traced tonight, not yet verified by actually reading/running the code)

In `scrapers/fl/bills.py`, `_process_bill_list()`:

```python
def _process_bill_list(self, bill_list):
    try:
        for item in bill_list.do_scrape():
            try:
                ...
                yield item
                ...
            except Exception as e:
                self._consecutive_failures += 1
                self.logger.error(f"Error processing item: {e}")
                ...
    except Exception as e:
        # our allow_partial_scrape logic lives here
        is_rejection = "reject" in str(type(e).__name__).lower() or "reject" in str(e).lower()
        if is_rejection and self.allow_partial_scrape:
            self.logger.warning(...)  # swallow, stop cleanly
        else:
            raise  # <-- this is what kills the whole scrape
```

**Hypothesis:** `HouseSearchPage` isn't fetched inside the *inner* try/except's protected region.
`BillDetail.process_page()` does `yield HouseSearchPage(self.input)` -- and per spatula's own
`_to_items()` (the recursive `yield from item._to_items(scraper)` in the traceback), a yielded
sub-page like `HouseSearchPage` gets fetched **inline**, synchronously, as part of *advancing the
`bill_list.do_scrape()` generator to produce the next item* -- not as part of processing an
already-obtained item. That means the fetch happens during the implicit "get next item" step of
`for item in bill_list.do_scrape():`, which is **outside** the inner `try/except` (that one only
wraps what happens *after* `item` is already in hand). It's still inside the *outer* try/except,
which is why we see it land in the `except Exception as e:` block with our `allow_partial_scrape`
logic -- but since a `ReadTimeout` isn't a "rejection" (`is_rejection` is `False`), it falls
through to `else: raise`, which kills the entire remaining scrape instead of just skipping this
one bill.

**If this hypothesis is right**, the fix is to make the outer except handler (or a wrapper further
down, closer to where `HouseSearchPage` is actually fetched) treat ordinary transient network
errors (`ReadTimeout`, `ConnectionError`, etc. -- the ones that already exhausted their own
per-request retries) the same way as "skip this one bill, log it, keep going" rather than
"crash the whole session." This is different from the `allow_partial_scrape` question (which is
about *bot-detection* specifically) -- this is about *ordinary transient failures on one bill*
that shouldn't cost you the other ~1,899 independent bills.

## Where these fixes actually live right now, and how to update them

**All three fixes (the two already-merged-into-our-branch ones, plus whatever you build for the
single-bill-failure issue) live only on the Tinyproxy-path custom docker image, not on the
official `openstates/scrapers:latest` image.** `fl-legislation`'s live scrape workflow is
currently running *from that custom image*, not upstream, via a temporary override. Until PR
#5724 merges and OpenStates cuts a new official image, this custom image is the only place any
of tonight's fixes (or a future single-bill-failure fix) actually take effect.

**To make a code change and get it running for real:**

1. `cd ~/tad_code.nosync/current/openstates-scrapers && git branch --show-current` -- **confirm
   it says `fix/fl-streaming-bills` before touching anything.** This exact mistake (checkout
   silently drifted to `main`) already cost us a full night of testing the wrong image once
   tonight. If it's not on that branch: `git checkout fix/fl-streaming-bills`.
2. Make your code edit(s) in `scrapers/fl/bills.py` (or wherever the actual fix lands).
3. Rebuild and push the image (must be `linux/amd64` -- your Mac is arm64, and GitHub-hosted
   runners are amd64, so a native build silently produces the wrong architecture):
   ```
   docker buildx build --platform linux/amd64 -t ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test --push .
   ```
4. **Verify the fix actually landed in the built image before trusting it** -- don't skip this,
   it's exactly what caught the branch-drift mistake:
   ```
   docker pull ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test
   docker run --rm --entrypoint /bin/bash ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test \
     -c "grep -n '<something from your new fix>' /opt/openstates/openstates/scrapers/fl/bills.py"
   ```
5. That's it for deployment -- `fl-legislation`'s workflow already points at this exact image tag
   (`docker-image: ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test` in
   `govbot-openstates-scrapers/fl-legislation/.github/workflows/openstates-scrape.yml`), so the
   *next* dispatch automatically picks up whatever you just pushed. No workflow edit needed unless
   you're changing which image tag it points to.
6. **Also commit and push the same code change to the `fix/fl-streaming-bills` branch itself**
   (the actual git branch, separate from the docker image) -- this is the head branch of PR
   #5724 on `tamara-builds/openstates-scrapers`, so pushing there updates the open PR
   automatically. The docker image and the PR branch are two different things that both need
   updating; rebuilding the image alone does *not* update the PR, and pushing to the branch alone
   does *not* redeploy the image -- you need both steps.
7. To dispatch a test run once redeployed: self-hosted (recommended, given the 6-hour
   GitHub-hosted ceiling and that a full FL session runs close to that long) --
   `gh workflow run openstates-scrape.yml -R govbot-openstates-scrapers/fl-legislation -f use-self-hosted=true`.
   Check for a concurrency conflict first (`gh run list -R govbot-openstates-scrapers/fl-legislation -w openstates-scrape.yml -L 3`)
   -- only one run can be active at a time, so cancel any stale queued/in-progress run first if
   you want yours to start immediately.

## Should we update PR #5724 to say we're still working on it?

Yes -- worth a short comment noting a third issue was found (single-bill failures killing the
whole session) and that a follow-up is coming, so the maintainer doesn't read the current silence
as "done, ready for final review" or assume the thread's gone stale. Doesn't need to include the
fix yet, just flags that more is coming before they spend more review time on the current state.

## What to actually do when picking this up

1. Read `scrapers/fl/bills.py` fresh (branch `fix/fl-streaming-bills`,
   `~/tad_code.nosync/current/openstates-scrapers`) -- confirm the current exact structure of
   `_process_bill_list`, `BillDetail.process_page()`, `HouseSearchPage`, and how spatula's
   `_to_items()`/`do_scrape()` actually walks yielded sub-pages. Don't trust this doc's line
   numbers/code snippets blindly -- re-verify against the live file.
2. Confirm the hypothesis: does a per-bill `HouseSearchPage` failure really land in
   `_process_bill_list`'s *outer* except rather than the *inner* one? (Could test locally by
   mocking a `HouseSearchPage` fetch to always raise, running a small scrape, and seeing which
   except block actually catches it -- or just carefully trace spatula's generator mechanics by
   reading `spatula/pages.py`'s `_to_items`/`_paginate`/`do_scrape` methods, already fetched once
   tonight to `/tmp` if that scratchpad still exists, otherwise re-fetch from
   `openstates/spatula` on GitHub.)
3. Design the fix: most likely, catch transient network exceptions (not rejections) at the point
   closest to the `HouseSearchPage`/`HouseBillPage` fetch (e.g., wrap the `yield HouseSearchPage(...)`
   in `BillDetail.process_page()` in its own try/except that logs and continues), OR broaden the
   outer except's logic to distinguish "this bill's house-side data failed, skip just that" from
   "something session-wide is wrong, stop." Be careful not to accidentally swallow *real*
   systemic problems (e.g., don't want a broken selector or a genuine site outage silently
   producing a mostly-empty dataset that looks successful).
4. This is a genuinely separate, smaller PR from #5724 -- probably don't bundle it into the same
   PR, since #5724 is already under maintainer review for a different, larger reason (the
   `list()`/streaming behavior + `allow_partial` opt-in). A follow-up PR referencing #5724 and
   citing this exact failure (bill 66, 2026-07-24 run) as the motivating example would be a clean,
   well-evidenced contribution.

## Current state / what's already true, no need to re-verify

- PR #5724: opt-in `allow_partial` flag + `timeout=10` fix, pushed and CI-green, awaiting
  maintainer re-review. Not yet merged.
- `ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test` (amd64) is the correctly-patched test
  image, confirmed via direct inspection to contain both fixes. Digest as of tonight:
  `sha256:10f506ff4e2deac03aa8ac99b34011c620f5ce73f8e2557705386fa431b7b49b`. (Watch out: an
  earlier build of this same tag was accidentally built from vanilla `main` because the local
  git checkout had drifted off the feature branch -- always verify branch + grep the built
  image's actual file contents before trusting a "fixed" image again.)
- `fl-legislation`'s live workflow (`govbot-openstates-scrapers/fl-legislation/.github/workflows/openstates-scrape.yml`)
  still has a temporary `docker-image: ghcr.io/tamara-builds/openstates-scrapers:fl-fix-test`
  override in it, from testing. Revert this to the default once PR #5724 merges and a real
  `openstates/scrapers:latest` image is rebuilt upstream with the fix.
- 413 real bills are committed to `_data/fl` in that repo as of tonight -- first real progress
  since 2026-07-02.
- `docs/src/state-status-reference.md` and `tamara-notes/state-problems.md` have the broader FL
  writeup and status; this doc is specifically about the narrower "one bill kills the whole run"
  question.
