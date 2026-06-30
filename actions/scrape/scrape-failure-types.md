# Scrape Failure Types

Reference for classifying scraper failures. Used to drive alerting behavior and
distinguish between states that are **actively blocking access to public data** vs.
states that simply have no new data available.

This distinction matters: a state blocking our scraper should fail loudly even if
fallback data exists, so stale data doesn't quietly accumulate unnoticed.

---

## Network Layer — Before Any HTTP Happens

| Code | Error | Meaning | Alert? | Use Fallback? |
|---|---|---|---|---|
| `N1` | `ConnectionRefusedError [Errno 111]` | Server actively rejecting the TCP connection. Firewall or server explicitly saying no. | 🚨 Yes, loudly | Yes — but surface stale data warning |
| `N2` | `TimeoutError [Errno 110]` (persistent) | Packets being dropped silently. Could be silent IP block or site genuinely down. Ambiguous — check if transient or consistent. | ⚠️ Yes | Yes |
| `N3` | `ConnectionResetError` | Connection established then immediately killed. Often a WAF (Web Application Firewall) detecting scraper behavior. | 🚨 Yes, loudly | Yes — but surface stale data warning |
| `N4` | DNS resolution failure | Domain doesn't resolve at all. Rare but possible state-level block. | 🚨 Yes, loudly | Yes — but surface stale data warning |

---

## HTTP Layer — Server Responds But Refuses to Cooperate

| Code | Error | Meaning | Alert? | Use Fallback? |
|---|---|---|---|---|
| `H1` | `403 Forbidden` | Server is up but explicitly denying access. Could be IP-based, User-Agent filtering, or geo-block. | 🚨 Yes, loudly | Yes — but surface stale data warning |
| `H2` | `401 Unauthorized` | API key missing, expired, or revoked. | ⚠️ Yes | Maybe — depends on whether prior data is valid |
| `H3` | `429 Too Many Requests` | Rate limited. Temporary throttle. | ℹ️ Retry first | No — retry before falling back |
| `H4` | `503 Service Unavailable` | Server temporarily down or overloaded. | ℹ️ Retry first | Yes if retries exhausted |

---

## Scraper Layer — Connected and Got Data, But Something's Wrong

| Code | Error | Meaning | Alert? | Use Fallback? |
|---|---|---|---|---|
| `S1` | `ScrapeError: no objects returned` | Scraper ran cleanly; legislature has no bills in current session. **Genuinely benign.** | ✅ No | Yes — silently |
| `S2` | `ValueError: ftp:// contains no matching files` | Same as S1, FTP source variant. Legislature out of session. **Genuinely benign.** | ✅ No | Yes — silently |
| `S3` | `AssertionError: Session ID not in bill list` | Session config is stale; scraper doesn't know about the current session year. Needs scraper update. | ⚠️ Yes | Yes |
| `S4` | `KeyError: 'field_name'` | Site changed its HTML/JSON structure; scraper expected a field that no longer exists. | ⚠️ Yes | Yes |
| `S5` | `ValueError: not enough values to unpack` / `IndexError` | Same class as S4 — site structure changed, parsing broke. | ⚠️ Yes | Yes |
| `S6` | `ScrapeValueError: validation failed` | Data was fetched but fails OCD schema validation. Data quality issue. | ⚠️ Yes | Partial |

---

## Known State Examples (as of 2026-06-30)

| State | Error Type | Notes |
|---|---|---|
| tx | ✅ Resolved | Was `N1` — self-hosted runner on Tamara's laptop bypasses IP block. |
| nh | `N2` — Persistent timeout | `gc.nh.gov` timing out. Out of session — paused by automation. |
| wi | `N2` — Transient timeout | `docs.legis.wisconsin.gov` intermittent; not consistent. |
| ct | `S1` — Out of session | `CTBillScraper` returns 0 objects. Paused by session automation. |
| nm | `S2` — Out of session | NM FTP has no files. Paused by session automation. |
| az | `S3` — Session config | `AssertionError: Session ID not in bill list`. Stale session mapping — re-check when 2027 session opens. |
| dc | ✅ Resolved | Was `S6` — PRs #5706 and #5711 merged upstream. |
| mp | `S6` — Validation | `ScrapeValueError: validation of Bill failed`. OCD schema mismatch. No session data in OpenStates. |
| hi | `S4` — Site structure | `KeyError: 'Report Title'`. Hawaii site changed structure. Out of session — paused by automation. |
| nj | ✅ Resolved | Was `S4` — PR #5707 merged upstream. |
| la | `S5` — Site structure | `ValueError: not enough values to unpack (expected 5, got 4)`. Out of session — paused by automation. |
| tn | `S5` — Site structure | `IndexError: list index out of range`. TN site structure changed. Out of session — paused by automation. |

---

## Intended Behavior by Category

```
N1, N3, N4, H1  →  ACTIVE BLOCK — fail loudly, surface warning, use stale fallback
N2, H4          →  CONNECTIVITY — retry; if persistent, warn and use stale fallback
H2              →  AUTH FAILURE — warn; check API key secrets
H3              →  RATE LIMITED — retry with backoff; do not fall back yet
S1, S2          →  OUT OF SESSION — succeed silently, use stale fallback
S3, S4, S5, S6  →  SCRAPER BROKEN — warn; use stale fallback; needs upstream fix
```

---

## TODO

- [x] Encode `failure_type` and `is_active_block` fields in `scrape-summary.json` — done in `scrape.sh`
- [x] Surface stale-data age in GitHub Actions summary when fallback is used — done in `action.yml`
- [x] For active blocks (N1, N3, N4, H1): post a visible `::error::` annotation even when fallback succeeds — done in `action.yml`
- [x] Investigate TX specifically — confirmed GitHub Actions IP block; resolved via self-hosted runner
