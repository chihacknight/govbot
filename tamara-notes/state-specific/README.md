# State-Specific Tracking — Index

One file per state with a tracked issue. When a state has a problem, check here first for
whether it already has a file — if so, read it top-down before re-investigating from
scratch; if not, this is where its file goes once something's found.

**Convention**: each file is named `<two-letter-code>.md` (or `usa.md` for the federal
jurisdiction), covers that state's full known history in one place (not scattered across
session notes), and ends with a "Related" section cross-linking any other state whose issue
shares a root cause or was found in the same investigation. See `fl.md` for the fullest
example of the pattern (built specifically because FL's history was scattered across 15+
other files before being consolidated).

## States with open issues (as of 2026-10-03)

| State | Status | Summary | File |
|---|---|---|---|
| 🔴 PA | Broken, ongoing | 100% failure rate for 19+ days — confirmed IP-reputation block on the proxy's egress IP. Needs a new egress path; not fixed. | [`pa.md`](pa.md) |
| 🔴 VI | Broken, ongoing | Same symptom as PA, but confirmed as a likely genuine destination-side outage, not a block. Probably self-resolves; nothing to fix on our end. | [`vi.md`](vi.md) |
| 🟡 GU | Broken, not fixed | Real scraper bug — a bill version's empty `note` field fails schema validation and crashes the whole scrape. Root cause not yet traced into source. | [`gu.md`](gu.md) |
| 🟢 USA | Fix confirmed live, upstream PR filed | Unhandled `KeyError` on a Senate vote crashed the scrape, masked by a misclassified rate-limit annotation. Fix verified live 2026-10-03 (+263 net-new bills downstream). PR [#5847](https://github.com/openstates/openstates-scrapers/pull/5847) + issue [#1422](https://github.com/openstates/issues/issues/1422) filed, awaiting review. | [`usa.md`](usa.md) |
| 🟡 UT | Unresolved | `CommandError: no sessions` crashed the last run before pausing. Not yet root-caused (real bug vs. transient vs. expected out-of-session behavior mishandled). | [`ut.md`](ut.md) |
| 🟡 WI | Unresolved | Last run before pausing hit GitHub-hosted runners' 6-hour execution cap mid-scrape. Likely needs FL's self-hosted + longer-timeout fix; not confirmed. | [`wi.md`](wi.md) |
| 🟡 MA | Unresolved on latest finding | Last run before pausing was cancelled after a 24h runner-queue wait (same shape as FL, never started). Also has older, separate silent-data-loss history. | [`ma.md`](ma.md) |
| 🟢 CO | Low priority | Genuine, correctly-classified rate-limit (429) on its last run before pausing. Not a bug — will likely clear on next dispatch. | [`co.md`](co.md) |
| 🟣 FL | Long-running, mostly resolved | The deepest history here (streaming fix, timeout fix, per-bill resilience, proxy/runner saga). Several root causes fixed and confirmed working; a couple of threads (committee-vote regression, upstream PR limbo) still open. Read this one as the reference example of the per-state format. | [`fl.md`](fl.md) |

**Legend**: 🔴 actively broken, no fix yet · 🟡 unresolved or fix in flight · 🟢 low priority /
likely self-resolving · 🟣 long-running, mostly stable

## Scope note — this doesn't cover all 56 states yet

This index and the per-state files only exist for states investigated since 2026-10-02/03
(prompted by finding PA's and VI's masked failures while reviewing the 9 active states, then
auditing the 47 paused ones). **Most of the other ~47 states' historical issues are not yet
migrated here** — they're still scattered across the older docs in `archived_docs/`
(`state-problems.md`, `not-working.md`, `working-in-session.md`, `working-out-of-session.md`,
`scraper-health.md`, and others). Those aren't being bulk-migrated right now; the plan is to
build a file here for a state the next time it actually comes up with an issue, same as how
these first eight got created. If a state isn't listed above, check the older docs in
`archived_docs/` for any pre-2026-10 history before assuming it has none.

`docs/src/state-status-reference.md` is the public-facing, one-row-per-state summary table
(uses the same failure-type codes as this index and `scrape.sh`) — it predates this system,
went stale (last updated 2026-07-25, mostly `TBD`), and isn't automatically fed by anything
yet. Worth deciding later whether to revive it as a mechanically-generated summary of this
directory, rather than hand-maintained prose, now that the daily/weekly audits
(`actions/openstates-scrape-audits/`) produce structured per-state signal that could drive it.

## Related systems

- `actions/openstates-scrape-audits/` — the automated weekly/daily checks that now catch new
  instances of these problems going forward (bill-discovery flatline, per-run failures masked
  by fallback). This directory is where a human writes up what those checks (or manual
  investigation) actually found.
- `tamara-notes/archived_docs/` — historical investigation docs, including the two sessions
  this index's first entries were pulled from (`pa-vi-proxy-connectivity-2026-10.md`,
  `paused-states-audit-2026-10.md`) and the pre-2026-10 per-state history mentioned above.
