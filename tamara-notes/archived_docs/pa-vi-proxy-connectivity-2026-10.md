---
name: pa-vi-proxy-connectivity-2026-10
description: PA and VI scrapes have failed 100% of runs for 19+ days, silently masked by nightly fallback + green checkmarks. Root-caused via govbot-proxy VM diagnostics on 2026-10-03 -- two different causes, not one. SUPERSEDED -- split into tamara-notes/state-specific/pa.md and vi.md.
metadata:
  type: project
---

> **Superseded 2026-10-03.** This investigation's findings were split into the canonical
> per-state files `tamara-notes/state-specific/pa.md` and `tamara-notes/state-specific/vi.md`
> (part of moving to one-file-per-state tracking, indexed in
> `tamara-notes/state-specific/README.md`). Kept here for the full original narrative/session
> record — the per-state files are shorter and the ones to actually check for current status.

# PA and VI: sustained scrape failures, silently masked (found 2026-10-03)

## What was found

Reviewing the 9 currently-active OpenStates scrapers' latest runs (per
`chn-openstates-scrape.yml`'s active/paused list) turned up two states with masked
failures classified `UNKNOWN`: `pa` and `vi` (a third, `gu`, also showed up with a
different, unrelated `S6_VALIDATION` failure — a real scraper bug, empty `note` field
failing schema validation — tracked separately, not covered by this doc). PA and VI both
showed `✅ success` on every run — the failure is a `::warning::` annotation, fallback data
keeps the job green, and nothing pages on it.

Checked the last 10 scheduled runs for each (`gh run list` + annotation grep, going back to
2026-09-14 for PA and 2026-09-16 for VI — the oldest runs readily available): **every single
one failed identically.** Not intermittent — a sustained, 100% failure rate for at least 19
consecutive days on both states, both running entirely on stale fallback data the whole
time, invisible because of the standard fallback-masks-green-checkmark pattern (the exact
gap `actions/openstates-scrape-audits/` was built to close going forward — see below for
whether it would have caught this).

## The actual error (same for both states, every run)

```
urllib3.exceptions.ProxyError: ('Unable to connect to proxy', OSError('Tunnel connection failed: 500 Unable to connect'))
requests.exceptions.ProxyError: HTTPSConnectionPool(host='www.palegis.us', port=443): ...
```
(VI: `host='billtracking.legvi.org', port=8082` instead)

Both states are configured `runner: self-hosted` in `chn-openstates-scrape.yml`, which
routes them through the shared Tinyproxy host (`govbot-proxy`, GCE instance in project
`govbot-proxy-502322`, zone `us-central1-a`, external IP `34.57.23.77`). Classified by
`scrape.sh` as `UNKNOWN` because its regex classifier has no pattern for
`ProxyError`/`Tunnel connection failed`/`Unable to connect to proxy` — it only recognizes
target-site failure shapes (timeouts, 403/429/503, DNS failure), not "the proxy's own
tunnel to the target failed." Worth a future classifier addition (see "Open questions"
below) — not done as part of this investigation, which was diagnosis only.

## Root-cause diagnosis (via `gcloud compute ssh` into `govbot-proxy`, 2026-10-03)

Installed the `gcloud` CLI locally, authenticated, and SSH'd directly into the proxy VM to
run live diagnostics. Full findings:

1. **Tinyproxy itself is healthy** — running continuously for 2+ months (`active since
   2026-07-13`), correctly configured, port 8888.
2. **The VM's general network egress works fine** — reached `google.com` and, as a direct
   control, MI's real scrape target (`www.legislature.mi.gov`) without issue.
3. **No GCP-side egress firewall exists** — `gcloud compute firewall-rules list` shows only
   inbound rules (SSH, ICMP, internal, the proxy's own 8888 port, RDP). GCP's default is
   allow-all-egress, and nothing here overrides that.
4. **Direct connection from the VM to both target hosts times out** — DNS resolves cleanly
   for both (`www.palegis.us` → `216.157.112.153`, `billtracking.legvi.org` →
   `20.232.220.11`), but the TCP connection itself never completes (10s timeout, no
   response at all). `traceroute` to `palegis.us` reaches a real hop in Philadelphia (hop 4,
   Level3/Lumen) then goes completely silent through hop 15 — consistent with something
   dropping the connection right around the destination's edge, not a routing failure
   upstream.

**Confirming whether this is IP-specific**: ran the identical requests from a second,
unrelated network (a home/residential IP, `207.229.172.46`) as a control:

- **`palegis.us` (PA): reachable from the residential IP** — full TLS handshake, real HTTP
  response — but returns **`403 Forbidden`**, not a timeout. A 403 means the site is up and
  its WAF is actively responding at the HTTP layer; a silent TCP-level timeout (no response
  at all) from the GCP IP means the block happens *before* any HTTP request is even sent.
  This is the classic signature of a WAF/anti-bot rule that soft-challenges (403) residential
  IPs but hard-drops (silent timeout) known datacenter/cloud-provider IP ranges. **Confirmed:
  an IP-reputation block specifically on `34.57.23.77` (or GCP's IP range generally), not a
  general outage.**
- **`billtracking.legvi.org` (VI): also times out from the residential IP**, identically to
  the GCP VM. Since it fails the same way from two completely unrelated networks, this is
  **not** IP-targeted — the VI bill-tracking server itself appears to be genuinely down or
  unreachable right now, independent of source.

**So the two states have different root causes, despite an identical symptom:**
- **PA**: the destination is up, but actively blocking this proxy's IP specifically.
- **VI**: the destination itself appears to be down/unreachable, full stop.

## What this means, practically

- **PA**: scraping PA from this infrastructure will keep failing until either (a) the egress
  IP changes to one not on whatever blocklist `palegis.us` is using, or (b) PA's site
  un-blocks `34.57.23.77` specifically (unlikely to happen on its own). A new egress IP (new
  VM, different proxy, or a rotating-IP solution) is the realistic fix; not attempted as part
  of this investigation.
- **VI**: likely needs no infra change on our end — more a "wait and periodically recheck"
  situation, though worth a quick check of whether VI's own site is more broadly reported
  down (not checked here; outside what's testable from this infra).
- **Neither required a GCP firewall change or a tinyproxy config fix** — both of those were
  directly ruled out during diagnosis, which is worth remembering before re-investigating
  this from scratch later.

## Would the new daily/weekly audits have caught this?

Not yet, but they will going forward — with one timing nuance. `scrape.sh`'s
`failure_type`/`error_summary` fields (added in PR #193, 2026-10-03) are what
`actions/openstates-scrape-audits/daily-scraper-error-digest.py` reads; PA's and VI's past
19 days of runs predate that change, so there's no retroactive signal to backfill from. Both
states' `failure_type` is `UNKNOWN` (not one of the auto-benign `NONE`/`S1_*`/`S2_*`
prefixes), so **the very next run that happens after the fix merged will surface in the
digest** — assuming the block is still active by then, which is likely given its 19-day
consistency. Confirmed this is the correct read of the digest's noise-filtering logic before
writing this down, not guessed.

## Open questions / not done here

- Whether to add a `ProxyError`/`Tunnel connection failed` pattern to `scrape.sh`'s
  classifier (would bucket this as something more specific than `UNKNOWN`, maybe its own
  `H5_PROXY_FAILURE`-style code, or folded into the existing active-block codes since it is
  functionally an active block, just surfaced through the proxy layer). Not built — flagging
  for a future session per the "don't guess ahead of a confirmed pattern" approach the daily
  digest's `NOISE_PATTERNS` already follows.
- Whether `palegis.us`'s block is literally keyed to `34.57.23.77` or to GCP's IP range more
  broadly (would matter for whether spinning up a *new* GCP VM actually fixes it, or just
  moves the same block to a new IP in the same range). Not tested.
- VI's actual outage cause/duration — not independently verifiable from this infra.
