# Scraper Problem Taxonomy

All 56 jurisdiction scrapers audited as of **2026-07-02**. Most failures fall into five root causes.

---

## 1. Cloud IP Blocking / Throttling

Government sites detect and block GitHub-hosted runner IPs (Azure ranges).

**Fix**: Run from a home-network self-hosted runner.

| State | Count | Pattern | Status |
|-------|------:|---------|--------|
| TX | — | Hard block — `capitol.texas.gov` refuses Azure IPs | ✅ Self-hosted runner active |
| MA | — | Throttling — `malegislature.gov` ramps response time to 300s+ then drops | ✅ Self-hosted runner active; run in progress |
| FL | — | No block, but serial per-bill scraping exceeds the 6-hour GitHub Actions cap | ✅ Self-hosted runner queued (after MA) |
| CT | 0→1,283 | Azure IPs blocked by CT FTP server — `ftp.cga.ct.gov` returns empty bill list → "no objects returned". Confirmed 2026-07-02: 1,283 bills in 17 min from home network. | ✅ Self-hosted runner active; issue [#1384](https://github.com/openstates/issues/issues/1384) 🔄 following up |
| TN | 37/5,400+ | Hard block — `wapp.capitol.tn.gov` returns N1_ACTIVE_BLOCK for Azure IPs | ✅ Self-hosted runner queued (after FL) |
| HI | 4 | Cloudflare WAF blocks all bill pages — `KeyError: 'Report Title'` on every bill | ⚠️ Issue [#1383](https://github.com/openstates/issues/issues/1383) closed by maintainer — anti-WAF out of scope for OSS; use `HTTPS_PROXY` env var |
| AZ | 4 | Sucuri WAF blocks the `setsession.php` POST used to initialize scraping | ⚠️ Issue [#1382](https://github.com/openstates/issues/issues/1382) closed by maintainer — anti-WAF out of scope for OSS; use `HTTPS_PROXY` env var |

**Note on the runner**: One physical runner (Tamara's MacBook, `~/actions-runner/`) is registered at the org level and covers TX, MA, FL, and TN. Digital Ocean droplet could replace this for always-on reliability.

---

## 2. FTP Data Sources

Some state sites publish legislative data exclusively over FTP. The original diagnosis ("scrapelib can't handle `ftp://`") was incorrect — scrapelib does handle FTP via a `urllib.request` wrapper under the hood. However, both NM and CT still produce zero bills in our environment. The failure manifests differently for each.

**NM**: Scrapelib makes the FTP request successfully (`INFO scrapelib: GET - 'ftp://www.nmlegis.gov/other/'`) but the directory listing it returns doesn't match the regex in `_init_mdb` that looks for `LegInfo26.zip`. When tested directly with `urllib.request.urlopen()`, the listing matches fine. Likely cause: scrapelib's response wrapper changes the format of the raw FTP directory listing in a way that breaks the regex.

**CT**: Confirmed Azure IP block on CT's FTP server (`ftp.cga.ct.gov`). CT uses FTP for the initial bill list (`bill_info.csv`) then HTTPS for individual bills. Azure blocks the FTP connection → empty bill list → `ScrapeError: no objects returned`. Three retries mid-session April 16, zero bills all of 2026. Self-hosted run 2026-07-02 from home network: **1,283 bills in 17 minutes**. Solution: self-hosted runner (infrastructure fix, not a code change). OpenStates issue [#1384](https://github.com/openstates/issues/issues/1384) open for awareness.

**Note**: OpenStates maintainer closed both issues as questioning the original diagnosis. We're following up with the specific tracebacks above.

| State | Count | FTP endpoints | Status |
|-------|------:|---------------|--------|
| NM | 4 | 1 FTP file (`LegInfo26.zip`) — published 10 weeks post-session | 🔄 Following up on issue [#1381](https://github.com/openstates/issues/issues/1381) with traceback |
| CT | 0→1,283 | FTP for bill list (`bill_info.csv`) + HTTPS for bills — Azure blocks FTP | ✅ Self-hosted runner confirmed working 2026-07-02; issue [#1384](https://github.com/openstates/issues/issues/1384) 🔄 open |

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
| WV | 45 | XPath selectors broken after site redesign — bill listing returns 0 results | PR [#5719](https://github.com/openstates/openstates-scrapers/pull/5719) open; maintainer disputes — need to provide failing scrape logs |
| VA | 0 | `--session` arg placed wrong in `scrape.sh` + hardcoded `session_id="20251"` in scraper | ✅ PR [#5717](https://github.com/openstates/openstates-scrapers/pull/5717) merged 2026-07-01; needs verification run |
| OK | 0→? | `(PROD)` suffix not stripped from session list — `CommandError: Session not found` | ✅ PR [#5718](https://github.com/openstates/openstates-scrapers/pull/5718) merged 2026-07-01; needs verification run |
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
| FTP data source / Azure IP block | NM, CT | CT: ✅ self-hosted runner. NM: regex mismatch in `_init_mdb` — following up with maintainers |
| Docker image timing | SD, UT, IN, ID | Yes — backfill dispatch (one command each) |
| Scraper/site bug | WV, VA, OK, LA, AR | Mostly yes — PRs filed or pending |
| Server down | VI | No — waiting on Virgin Islands legislature |

---

## What's In the Queue Right Now

1. **FL** — self-hosted backfill still pending (queued)
2. **WV** — respond to maintainer with failing scrape logs; backfill after PR #5719 merges
3. **VA** — verification run needed (PR #5717 merged 2026-07-01)
4. **OK** — verification run needed (PR #5718 merged 2026-07-01)
5. **NM / CT** — follow up with OpenStates maintainers with specific tracebacks
6. **SD / IN / ID** — backfill dispatch (API accessible, one command each)
7. **UT** — backfill dispatch after clearing GitHub Actions cache
