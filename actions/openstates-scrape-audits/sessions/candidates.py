"""Candidate events the re-audit found: likely failures, NOT confirmed. Kept apart from
history/known_events.py (the answer key) until Tamara confirms them. Days are UTC, inclusive."""
from typing import NamedTuple


class Candidate(NamedTuple):
    name: str
    start: str
    end: str
    states: frozenset
    evidence: str


CANDIDATES = [
    # From 07-22 to 08-08 about 55 runs a day were green but only 2-8 states a day brought anything
    # new; on 08-09, the first morning after govbot 37df675d (#112: the download cache, restored
    # from any earlier run and never revalidated by scrapelib, bounded to one UTC day), 19 states
    # brought new data at once. The 07-21 rebuild had just filled the cache. States listed: active
    # 07-14..07-21, nothing new 07-22..08-08 on green runs, new data on 08-09 (re-audit query).
    Candidate("download cache replay before #112", "2026-07-22", "2026-08-08",
              frozenset("ak az ia il ks la md me nc nj ny oh usa va vt wy".split()),
              "fleet: 2-8 states/day new on ~55 green runs; 19 states new on 08-09 after 37df675d (2026-08-08)"),
    # NJ: the same cache, for months. #112's own text: NJ "froze on a late-January 2026 snapshot
    # for ~7 months"; the formatted repo's newest action was 2026-01-28. The raw history agrees:
    # new data on 01-29, then only 547 votes on 06-30 (a separate file), then 08-09.
    Candidate("NJ download cache freeze (late-January snapshot)", "2026-01-30", "2026-08-08",
              frozenset({"nj"}), "37df675d (#112) commit text; raw history: new data 01-29, 06-30 (votes), 08-09"),
]
