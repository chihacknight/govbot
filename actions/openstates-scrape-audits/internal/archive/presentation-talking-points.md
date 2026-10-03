# Dec 15 presentation — talking points

Running list of concrete moments from this work worth telling as part of the data-side
story, not just a status report.

## 1. The MP "bill from the future" (found 2026-09-30/10-01)

**What happened**: Building the state-health audit, we found `mp-legislation`'s most
recent known bill action dated **2035-05-09** — almost 9 years in the future. Traced it
to one specific bill (HB 24-17) and one specific action ("Senate Final Reading").

**The twist, and why it's a good example**: it's not our bug. We checked the Northern
Mariana Islands legislature's own official site (cnmileg.net) directly, and it
literally shows "P-**05/09/35** SD1" — a real typo by their own clerical staff (almost
certainly meant 05/09/**25**; every other date on the same bill is 2025). Our scraper
faithfully captured exactly what the government published. The pipeline did its job
correctly; the authoritative source record itself has the error baked in.

**Why this is worth presenting**: it's a concrete, true story that demonstrates several
things at once —
- Government data is genuinely messy at the source, not just in scraping/parsing. Any
  system over 56 jurisdictions' worth of government record-keeping has to expect this.
- govbot's core principle (faithful, tamper-evident mirror of what was actually
  published — never silently "corrected") means we *don't* get to fix this by
  overwriting it with our own guess, even when we're confident what it should say. The
  raw action stays exactly as published.
- But a known-bad value shouldn't be allowed to quietly break *our own* derived
  tooling — the fix was a guardrail that stops an implausible date (an "occurred"
  action dated in the future) from corrupting the staleness-tracking watermark, while
  leaving the actual historical record completely untouched. Two different
  problems — "what did the government say" vs. "can we trust our own signal" — solved
  two different ways, neither one compromising the other.
- It's also a direct, real-world justification for the two-signal design (the
  government-date ratchet + the independent run-date activity counter): if the ratchet
  had been the only thing we had, this bug would have silently broken staleness
  detection for MP until the year 2035.

## 2. (space for more — add as they come up)
