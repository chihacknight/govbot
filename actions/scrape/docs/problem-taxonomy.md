# Scraper Problem Taxonomy

All 56 jurisdiction scrapers audited as of **2026-07-01**. 50/56 have data; 6 have serious gaps.
Most failures fall into five root causes.

---

## 1. Cloud IP Blocking / Throttling

Government sites detect and block GitHub-hosted runner IPs (Azure ranges).

**Fix**: Run from a home-network self-hosted runner.

| State | Count | Pattern | Status |
|-------|------:|---------|--------|
| TX | — | Hard block — `capitol.texas.gov` refuses Azure IPs | ✅ Self-hosted runner active |
| MA | — | Throttling — `malegislature.gov` ramps response time to 300s+ then drops | ✅ Self-hosted runner active; run in progress |
| FL | — | No block, but serial per-bill scraping exceeds the 6-hour GitHub Actions cap | ✅ Self-hosted runner queued (after MA) |
| TN | 37/5,400+ | Hard block — `wapp.capitol.tn.gov` returns N1_ACTIVE_BLOCK for Azure IPs | ✅ Self-hosted runner queued (after FL) |
| HI | 4 | Cloudflare WAF blocks all bill pages — `KeyError: 'Report Title'` on every bill | ❌ Issue [#1383](https://github.com/openstates/issues/issues/1383) filed; no fix yet |
| AZ | 4 | Sucuri WAF blocks the `setsession.php` POST used to initialize scraping | ❌ Issue [#1382](https://github.com/openstates/issues/issues/1382) filed; no fix yet |

**Note on the runner**: One physical runner (Tamara's MacBook, `~/actions-runner/`) is registered at the org level and covers TX, MA, FL, and TN. Digital Ocean droplet could replace this for always-on reliability.

---

## 2. FTP Data Sources

Some state sites publish legislative data exclusively over FTP. Scrapelib (the OpenStates HTTP library) cannot handle `ftp://` URLs — requests return no content rather than raising an error, so the scraper completes with 0 bills and exit code 0.

**Fix**: Replace `self.get("ftp://...")` with `urllib.request.urlopen(...)` in the scraper.

| State | Count | FTP endpoints | Status |
|-------|------:|---------------|--------|
| NM | 4 | 1 FTP file (`bills.txt`) — published after session ends | ❌ Issue [#1381](https://github.com/openstates/issues/issues/1381) filed; fix straightforward |
| CT | 4 | 5 FTP endpoints including a directory listing (`ftp.cga.ct.gov`) | ❌ Issue [#1384](https://github.com/openstates/issues/issues/1384) filed; more complex to fix |

**Contrast with AR**: Arkansas also has FTP data but uses an HTTPS wrapper (`arkleg.state.ar.us/Home/FTPDocument?path=...`) — scrapelib handles it fine.

---

## 3. Docker Image Timing

OpenStates adds new legislative sessions to scrapers via code commits. The Docker image `openstates/scrapers:latest` doesn't pick these up immediately. For short sessions (Jan–Mar), the image may not know the 2026 session exists until the session is almost or entirely over.

**Result**: Bills scraped only during the narrow window between "Docker image learns the session" and "session ends." Stale GitHub Actions caches then freeze that partial bill list indefinitely.

**Fix**: One-time manual dispatch on the legislation repo (to rescrape with the current Docker image, which now knows the full session). May also need to clear the Actions cache first.

| State | Count | Session dates | Docker learned session | Bills captured |
|-------|------:|---------------|----------------------|----------------|
| SD | 45 | Jan 14 – Mar 30 | ~Mar 22 | 41/666 (6%) |
| IN | 47 | Dec 2025 – Feb 27 | ~Mar 23 | ~40/~1,000+ |
| UT | 28 | Jan 20 – Mar 6 | Late Feb | 3/1,016 (2026) + 5 complete (2025S2) |
| ID | 5 | Jan 12 – Apr 2 | Late Mar | 1 bill (HCR 020) |

All four: session is over, API/data is still accessible, backfill is a one-command trigger.
UT additionally needs the GitHub Actions cache cleared (cached bill list from early in session).

---

## 4. Scraper / Site Structure Bugs

Scrapers break when state websites redesign, change session identifiers, or add edge cases.

| State | Count | Root cause | Status |
|-------|------:|------------|--------|
| WV | 45 | XPath selectors broken after site redesign — bill listing returns 0 results | PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) open; backfill after merge |
| VA | 0 | `--session` arg placed wrong in `scrape.sh` + hardcoded `session_id="20251"` in scraper | PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) open + govbot PR [#52](https://github.com/chihacknight/govbot/pull/52) |
| OK | 0→? | `(PROD)` suffix not stripped from session list — `CommandError: Session not found` | PR [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) merged; needs verification run |
| LA | 7/525 | Crash fixed; bill search returns only ~7 results due to abbreviation/pattern issues | Issue [#1379](https://github.com/openstates/issues/issues/1379) open; waiting on maintainers |
| AR | 4 | Active special session 2026S1 has 2 bills (SB1, HB1001) in data source but scraper produces 0 with EXIT_CODE=0 | Root cause unclear — stale cache or silent validation failure; needs investigation |

---

## 5. External Infrastructure Down

| State | Count | Issue |
|-------|------:|-------|
| VI | 0 | `billtracking.legvi.org:8082` connection timeout — server-side outage, no code fix possible |

---

## Summary Table

| Root Cause | States Affected | Fixable By Us? |
|------------|----------------|----------------|
| Cloud IP block | TX, MA, FL, TN, HI, AZ | TX/MA/FL/TN: yes (self-hosted runner). HI/AZ: needs OpenStates scraper change |
| FTP data source | NM, CT | Yes — scraper code change (PR needed) |
| Docker image timing | SD, UT, IN, ID | Yes — backfill dispatch (one command each) |
| Scraper/site bug | WV, VA, OK, LA, AR | Mostly yes — PRs filed or pending |
| Server down | VI | No — waiting on Virgin Islands legislature |

---

## What's In the Queue Right Now

1. **MA** — self-hosted run in progress (5h+); merge PR [#53](https://github.com/chihacknight/govbot/pull/53) after it completes
2. **FL** — queued, triggers after MA run + PR merge
3. **TN** — queued after FL
4. **WV** — backfill after PR #5719 merges
5. **VA** — needs govbot PR #52 merge + apply-templates + one scrape run
6. **OK** — needs one verification run (PR merged)
7. **SD / IN / ID** — backfill dispatch (straightforward, API accessible)
8. **UT** — backfill dispatch after clearing GitHub Actions cache
