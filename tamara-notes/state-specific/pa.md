---
name: pa
description: PA scrape has failed 100% of runs for 19+ days via a confirmed IP-reputation block on govbot-proxy's egress IP, silently masked by fallback + green checkmarks. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# Pennsylvania

## Status: 🔴 Broken — sustained, ongoing, unresolved

**Active state** (`runner: self-hosted` in `chn-openstates-scrape.yml`), scheduled daily.

## What's wrong

Every scheduled run has failed with the identical error for **at least 19 consecutive days**
(checked 2026-09-14 through 2026-10-02, all 10 available runs in that window — 100% failure
rate). Each run still shows `✅ success` because it falls back to stale nightly data —
nothing pages on it.

```
urllib3.exceptions.ProxyError: ('Unable to connect to proxy', OSError('Tunnel connection failed: 500 Unable to connect'))
requests.exceptions.ProxyError: HTTPSConnectionPool(host='www.palegis.us', port=443): Max retries exceeded...
```

Classified `UNKNOWN` by `scrape.sh` — its regex classifier has no pattern for
`ProxyError`/`Tunnel connection failed`, only target-site failure shapes.

## Root cause (confirmed 2026-10-03, via `gcloud compute ssh` into `govbot-proxy`)

**Confirmed: an IP-reputation block on the proxy's egress IP (`34.57.23.77`), not a general
outage, not a GCP/tinyproxy config problem.**

- Tinyproxy itself: healthy (running 2+ months uninterrupted).
- The proxy VM's general network egress: healthy — reached `google.com` and MI's real scrape
  target (`www.legislature.mi.gov`) without issue as controls.
- No GCP egress firewall exists on this project (`gcloud compute firewall-rules list` shows
  only inbound rules).
- Direct connection from the proxy VM to `www.palegis.us` times out completely (DNS
  resolves fine to `216.157.112.153`, but the TCP connection never completes). `traceroute`
  reaches a real hop in Philadelphia (Level3/Lumen) then goes silent.
- **The confirming test**: the identical request from a second, unrelated network (a
  residential IP, `207.229.172.46`) gets a real HTTP response — **`403 Forbidden`** — not a
  timeout. A 403 means the site is up and its WAF responded at the HTTP layer; the GCP IP
  never even gets that far (silent TCP-level drop). This is the classic signature of a WAF
  that soft-challenges residential IPs but hard-drops known datacenter/cloud-provider IP
  ranges.

## What would actually fix this

Needs a different egress IP — either a new proxy VM (not guaranteed to help if the block is
keyed to GCP's IP range broadly, not just this one address — untested), or routing PA
specifically through non-cloud infrastructure. Not attempted yet. `palegis.us` un-blocking
`34.57.23.77` on its own is possible but not something to wait on.

## Would the new audits have caught this going forward?

Yes, from the next run after 2026-10-03 onward — `scrape.sh`'s `failure_type`/`error_summary`
fields (added same day) are what `actions/openstates-scrape-audits/daily-scraper-error-digest.py`
reads, and `UNKNOWN` is never treated as benign regardless of warnings. It just doesn't
retroactively cover the 19 days before the fields existed.

## Timeline

- **2026-09-14 (earliest checked) → 2026-10-02**: every single scheduled run fails
  identically on this proxy error. Not found/investigated until 2026-10-03 (discovered via a
  spot-check of the 9 currently-active states' latest runs, prompted by investigating a
  different, unrelated usa-legislation bug the same day).
- **2026-10-03**: root-caused via live SSH diagnostics into `govbot-proxy`. See "Root cause"
  above for the full evidence trail.

## Related

- `vi.md` — same symptom (`ProxyError`/`Tunnel connection failed`), found the same day,
  different root cause (VI's appears to be a genuine destination-side outage, not an
  IP block — see that file).
- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
