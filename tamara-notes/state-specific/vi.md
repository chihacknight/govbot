---
name: vi
description: VI scrape has failed 100% of runs for 19+ days with the same proxy-tunnel error as PA, but confirmed as a likely genuine destination-side outage, not an IP block. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# U.S. Virgin Islands

## Status: 🔴 Broken — sustained, ongoing, likely not fixable from our side

**Active state** (`runner: self-hosted` in `chn-openstates-scrape.yml`), scheduled daily.

## What's wrong

Every scheduled run has failed with the identical error for **at least 19 consecutive days**
(checked 2026-09-16 through 2026-10-02, all 10 available runs in that window — 100% failure
rate). Each run still shows `✅ success` because it falls back to stale nightly data.

```
urllib3.exceptions.ProxyError: ('Unable to connect to proxy', OSError('Tunnel connection failed: 500 Unable to connect'))
requests.exceptions.ProxyError: HTTPSConnectionPool(host='billtracking.legvi.org', port=8082): Max retries exceeded...
```

Classified `UNKNOWN` by `scrape.sh` — same gap as PA (no classifier pattern for
`ProxyError`/`Tunnel connection failed`).

## Root cause (confirmed 2026-10-03, via `gcloud compute ssh` into `govbot-proxy`)

**Looks like a genuine destination-side outage, not an IP-targeted block** (unlike PA's,
see `pa.md`, which has the identical symptom but a different confirmed cause).

- Direct connection from the proxy VM to `billtracking.legvi.org:8082` times out (DNS
  resolves fine to `20.232.220.11`, TCP connection never completes).
- **The confirming test**: the identical request from a second, completely unrelated
  network (a residential IP, `207.229.172.46`) **also times out, identically**. Since it
  fails the same way from two unrelated networks, this isn't IP-targeted — the VI
  bill-tracking server itself appears to be down or unreachable right now, independent of
  source.

## What would actually fix this

Probably nothing on our end — this looks like VI's own `billtracking.legvi.org` server is
down. Worth periodically rechecking (not on a fixed cadence yet) rather than treating as an
infra problem to solve. Not independently verified against any other outside source (e.g. a
status page) — only tested from the two networks available during this investigation.

## Would the new audits have caught this going forward?

Yes, from the next run after 2026-10-03 onward — same mechanism as PA (see `pa.md`'s
"Would the new audits..." section, identical reasoning).

## Timeline

- **2026-09-16 (earliest checked) → 2026-10-02**: every single scheduled run fails
  identically. Not found/investigated until 2026-10-03.
- **2026-10-03**: root-caused alongside PA via live SSH diagnostics into `govbot-proxy`;
  the residential-IP control test is what distinguished this from PA's IP-block (both hit
  the same proxy error, but only PA responded differently from the two networks).

## Related

- `pa.md` — identical symptom, found the same day, confirmed IP-block cause (contrast with
  this file's genuine-outage conclusion).
- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
