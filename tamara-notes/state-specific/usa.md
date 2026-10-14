---
name: usa
description: USA's scrape crashed on an unhandled KeyError on a Senate vote result, got misclassified as a rate-limit issue, fell back to nightly data invisibly. Fix merged upstream 2026-10-06, confirmed live in the official image, custom docker_image override reverted 2026-10-13. Closed. One of the per-state files indexed in tamara-notes/state-specific/README.md.
metadata:
  type: project
---

# USA (Federal)

## Status: 🟢 Resolved — fix merged upstream, running on the official image again

**Active state** (`runner: self-hosted`, `scrape_timeout_minutes: 720`) in
`chn-openstates-scrape.yml`, scheduled daily.

## What was wrong

Scrape crashed with an unhandled exception during Senate vote processing:

```
File "scrapers/usa/bills.py", line 722, in scrape_senate_votes
    result = self.senate_statuses[result_text]
KeyError: 'Concurrent Resolution Rejected'
```

`senate_statuses` (a hardcoded dict mapping Senate roll-call result text to pass/fail) had
`"Concurrent Resolution Agreed to"` mapped but was missing its `"Rejected"` counterpart —
confirmed on a real Senate vote on H.Con.Res. 86, 119th Congress (run
[36994226932](https://github.com/govbot-openstates-scrapers/usa-legislation/actions/runs/36994226932),
2026-10-02).

**Compounding bug, found the same day**: `scrape.sh`'s failure classifier misreported this
as `H3_RATE_LIMITED` — its regex for detecting HTTP 429s (`(^|[^0-9])429([^0-9]|$)`) false-matched
the literal bill number "HR 429" appearing dozens of times in the scrape log (e.g.
`BILLSTATUS-119hr429.xml`, `save bill HR 429`), beating the correct `KeyError` → `S4_SITE_STRUCTURE`
classification in `scrape.sh`'s if/elif chain. The run fell back to nightly data and showed
green, with the annotation claiming a rate-limit issue that never happened.

## Fixes applied

1. **The actual bug**: `"Concurrent Resolution Rejected": "fail"` added to `senate_statuses`
   in `scrapers/usa/bills.py`. Pushed to `fix/usa-senate-vote-concurrent-resolution-rejected`
   on `tamara-builds/openstates-scrapers` (fork), PR filed upstream:
   [openstates/openstates-scrapers#5847](https://github.com/openstates/openstates-scrapers/pull/5847),
   companion issue [openstates/issues#1422](https://github.com/openstates/issues/issues/1422).
   **Not yet merged.**
   - Reproduced and verified locally offline first: built a minimal `roll_call_vote` XML
     fixture matching the real schema, confirmed it crashes with the exact same `KeyError`
     against unfixed code, then confirmed it resolves correctly (`result='fail'`) after the
     fix.
   - Built the real Docker image (`ghcr.io/tamara-builds/openstates-scrapers:usa-fix-test`,
     linux/amd64) from the fix branch and verified via `docker run --entrypoint bash ...
     grep` that the fix is actually present in the pushed image (not just "built
     successfully" — the exact mistake that cost a full night once on FL, see `fl.md`).
2. **The masking bug**: `scrape.sh`/`action.yml` now always surface the real exception text
   (`ERROR_SUMMARY`) alongside the `FAILURE_TYPE` bucket guess, in both the GHA annotation
   and the committed `.windycivi/warning_history.json`. This doesn't fix the regex
   misclassification itself (still unfixed — a `429` false-positive could recur on any state
   with a bill numbered 429), but it means a wrong bucket can no longer hide the real cause.
   Merged via PR #193.

## Live verification: ✅ confirmed working (2026-10-03)

`usa-legislation`'s scrape workflow temporarily points at the custom fix image via the
`docker_image` config field (PR #196, applied live via `apply.py --test-states usa`) — same
pattern as FL's existing override. Dispatched a real live test run
([37092845888](https://github.com/govbot-openstates-scrapers/usa-legislation/actions/runs/37092845888))
to confirm the fix resolves the real incident end-to-end, not just the offline repro.

**Result: clean success.** Completed in 1h39m29s (faster than the original crash-and-retry
run's ~2h22m, since no retries were needed) with **zero scrape-failure annotations** — only
the usual unrelated Node.js/Ubuntu-runner deprecation notices. No `KeyError`, no real
traceback in the job log (the only "Traceback" string match was the bash classifier's own
grep logic checking for one, not an actual error). The specific `"Concurrent Resolution
Rejected"` vote didn't recur in this run's dataset (congressional data shifts run to run),
so this doesn't re-exercise that exact line — but the offline repro already proved the fix
handles it directly, and this run proves the fix doesn't break anything else in the real
pipeline.

## What's still open

- **Resolved 2026-10-13**: PR #5847 merged upstream 2026-10-06; confirmed the official
  `openstates/scrapers:latest` image was actually rebuilt with it (not just merged — checked
  Docker Hub's `last_updated` and the raw source directly, same discipline as everywhere else
  in this doc) before reverting `usa`'s `docker_image` override in `chn-openstates-scrape.yml`
  and dispatching a confirmation run
  ([38498947245](https://github.com/govbot-openstates-scrapers/usa-legislation/actions/runs/38498947245))
  on the real official image.
- Still need to delete the now-unused `ghcr.io/tamara-builds/openstates-scrapers:usa-fix-test`
  image (version id `1329967562`) — blocked on the `gh` token's package-delete scope, left as a
  manual GitHub UI step.
- The `429` regex false-positive itself is still not fixed — only its symptom (a hidden error)
  is mitigated. A future bill numbered 429 in any state's log could trigger the same
  misclassification again. Deliberately not "fixed" by hardening the regex further — see
  `actions/openstates-scrape-audits/README.md`'s reasoning on why surfacing the real error
  text was preferred over chasing a perfect classifier.

## Timeline

- **2026-10-02**: incident occurred live; investigated same day, root cause found for both
  the `KeyError` and the `429` misclassification.
- **2026-10-03**: fix built, tested offline, built into a verified Docker image, live test
  dispatched and **confirmed clean** (1h39m29s, zero failure annotations) — the downstream
  `govbot-data/usa-legislation` commit showed +263 distinct net-new bills vs. the last commit,
  real confirmation the fix is producing genuine new data, not just passing CI. `scrape.sh`/
  `action.yml` masking fix merged (#193). `docker_image` override applied (#196). Upstream PR
  [#5847](https://github.com/openstates/openstates-scrapers/pull/5847) and issue
  [#1422](https://github.com/openstates/issues/issues/1422) filed.

## Related

- `gu.md` — same general pattern (one bad record crashes the entire scrape).
- `fl.md` — same "verify the image actually contains the fix before trusting it" lesson,
  learned there first.
- `tamara-notes/state-specific/README.md` — the index of all states with open issues.
