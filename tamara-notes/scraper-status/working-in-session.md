# Working, currently in session (8 states)

Scraper confirmed `✅` in the 2026-07-21 full 56-state audit, and the state is currently
**in session** per LegiScan's `session-calendar-2026.md` (as of 2026-07-13). These are the
states where fresh bill activity is actively happening *and* we're capturing it — the ones
worth spot-checking for new/updated bills if a downstream consumer asks "is this current."

**Caveat:** same as `working-out-of-session.md` — "✅" is last-verified 2026-07-21, not
continuously monitored.

**Not included here despite being in-session:** MA, MI, MP, VI — all currently in session per
LegiScan, but their scraper status is either unverified, still being actively fixed, or a
genuine known dead end. See `not-working.md`.

| State | Notes |
|---|---|
| CA | 2025-2026 Biennium, in session through ~2026-08-31 (LegiScan end date estimated). |
| DC | 26th Council, in session through end of year. |
| GU | Year-round legislature, sessions called as needed — effectively always "in session." |
| NC | 2025-2026 Biennium. Self-hosted required — was NOT an IP block, was frozen ~7 months for a different reason (see `scraper-health.md`). |
| NJ | 2026-2027 Biennium, just started. |
| OH | ✅ Confirmed clean 2026-07-24 (identifier check: 2,452 bill files, 2,452 distinct, zero dupes). |
| PA | ✅ Confirmed clean 2026-07-24 (identifier check: 4,857 bill files, 4,857 distinct, zero dupes). |
| USA | ✅ Confirmed clean 2026-07-26 — shrink-guard identifier-check fix landed 17,574 real bills repeatedly, replacing a 48,714-file baseline (half was stale duplicates). Also the test case for the commit-summary-label fix (PR #97). |
