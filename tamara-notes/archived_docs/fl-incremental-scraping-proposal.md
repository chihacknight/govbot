# FL Incremental Scraping — Problem Statement & Proposal

## Context

We are running the Florida scraper from a home-network self-hosted runner (not Azure IPs). The scraper successfully authenticates and begins fetching bills from both `flsenate.gov` and `flhouse.gov`. The problem is not IP blocking — it's application-layer bot detection from `flhouse.gov`, which returns HTTP 200 with a "Request Rejected" HTML page after a sustained scraping session.

**Scale**: Florida's 2026 regular session has approximately 8,000 bills. The scraper can process roughly 160 bills per run (about 1–2 hours) before `flhouse.gov` triggers bot detection and the session is terminated.

At 160 bills per run, a full scrape of FL would require ~50 daily runs. This makes full coverage impractical without some form of incremental/checkpoint support.

---

## Current Failure Mode

The FL scraper's `scrape()` method wraps its generator in `list()`:

```python
yield from retry_on_connection_error(
    lambda: list(do_scrape_with_retry()),  # list() forces full materialization
    max_retries=3,
    ...
)
```

`list()` forces the entire session's generator to fully materialize before a single bill is yielded to OpenStates and written to disk. When spatula raises `RejectedResponse` at bill ~160, `list()` propagates the exception rather than returning a partial list — resulting in **zero bills saved** despite 1–2 hours of successful scraping.

We have a PR ready that removes `list()` and adds graceful `RejectedResponse` handling so bills are saved as they're yielded (streaming). This is a prerequisite fix regardless of how incremental scraping is handled.

---

## The Incremental Scraping Problem

Even with the streaming fix, each run only captures ~160 bills before bot detection. To accumulate all ~8,000 bills, we need a way to:

1. **Remember** which bills were successfully captured in previous runs
2. **Skip** already-captured bills on the next run (so the bot-detection budget is spent on new bills)
3. **Merge** newly captured bills with the previously captured set

---

## Proposed Approach

### Option A: Index/Bill-ID Cursor

Store the last successfully scraped bill identifier (or list position) as a cursor. On the next run, pass it as a parameter to the scraper, which skips all bills before that point.

**What we'd need from the scraper:**

```python
# In scrape() or _process_bill_list():
start_after = os.environ.get("FL_START_AFTER_BILL", None)
skip = bool(start_after)

for bill in bills:
    if skip:
        if bill.identifier == start_after:
            skip = False
        continue  # don't fetch detail, don't hit flhouse.gov
    yield from process_bill(bill)
```

**Infrastructure around it (our side):**

- After each successful partial run, write `{ "last_bill": "HB0164" }` to the legislation repo
- Next run reads that file and passes `FL_START_AFTER_BILL=HB0164` into the Docker container via env var
- Output directory accumulates bills across runs rather than being wiped each time

**Tradeoffs:**

- Simple to reason about
- Requires the scraper to expose a start-position parameter
- Requires the output layer to merge rather than replace on each run
- Works well for ended sessions (bills are static); for active sessions, bills near the cursor may need re-scraping to pick up status changes

### Option B: Bill-Level Caching (Skip Already-Fetched Bills)

Rather than a positional cursor, the scraper checks whether a bill's detail page has already been cached and skips fetching it again. With `--fastmode`, scrapelib already caches HTTP responses in `_cache/`. If that cache persists across runs (it does on our self-hosted runner), the scraper naturally spends less time on already-processed bills.

**Limitation**: This helps throughput but doesn't prevent re-processing bill objects that are already in the output. It also depends on cache not being cleared between runs.

### Option C: Session-Level Parallelism

Run multiple Docker containers in parallel, each responsible for a slice of the bill list (bills 1–500 in container A, 501–1000 in container B, etc.). This distributes the load and finishes in fewer wall-clock days.

**Limitation**: Requires the bill list to be deterministically ordered and sliceable, and still requires the scraper to support a range parameter.

---

## Question for OpenStates

Before building any of this: **does OpenStates already have a mechanism for checkpoint/resume scraping, or a recommendation for how to handle scrapers that regularly hit rate limits mid-session?**

We are aware of `--fastmode` (HTTP cache) and the retry logic in `retry_on_connection_error`, but neither addresses the case where a scraper reliably times out mid-session and needs to resume from where it left off across separate runs.

Any guidance on the preferred pattern — or an existing hook we can use — would be much appreciated before we build something custom.

---

## Related

- Streaming fix PR: removes `list()`, adds `RejectedResponse` handling — ready to submit
- FL scraper: `scrapers/fl/bills.py`
- Bot detection: `HouseSearchPage.accept_response()` lines 736–760 — detects "Request Rejected" HTML from `flhouse.gov`

- Example failing run (Actions log): https://github.com/govbot-openstates-scrapers/fl-legislation/actions/runs/28609385406
