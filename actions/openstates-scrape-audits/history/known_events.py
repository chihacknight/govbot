"""Failures we already know about, with dates: the answer key for the check replays (Q16), and the
stretches left out when a state's normal is measured (Q15).

Each event names the check expected to catch it. Dates are UTC days, inclusive. Sources are the
notes or the plan doc's Progress entries (section 7) where each was found or confirmed; a
mismatch between an event here and the history means one of them is wrong, so check both.

"No scrape" gaps are not listed: they are facts in the git history (no commit for N days), so
replay.py finds them itself (`commit_gaps`, gaps over 14 days, as the first-wave review measured).
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class Event(NamedTuple):
    state: str
    check: str            # the check expected to catch it (replay.CHECKS), or "" if none should
    start: str            # first day affected (UTC)
    end: str              # last day affected (UTC)
    what: str
    source: str


EVENTS = [
    # Frozen: scrapes kept being committed, nothing in them changed.
    Event("ky", "unchanged", "2026-01-08", "2026-07-14", "74 prefiled bills unchanged through the 2026 session",
          "Progress, WY/KY/AR step, finding 1"),
    Event("wy", "unchanged", "2025-12-03", "2026-07-14", "23 bills unchanged through the 2026 budget session",
          "Progress, WY/KY/AR step, finding 1"),
    Event("il", "unchanged", "2025-12-15", "2026-07-13", "8,648 bills unchanged (the Dec 2025 freeze)",
          "Progress, first wave; notes-by-state § IL"),
    Event("nc", "unchanged", "2025-11-28", "2026-07-13", "1,794 bills unchanged (the Dec 2025 freeze)",
          "Progress, first wave; notes-by-state § NC"),
    Event("pa", "unchanged", "2025-11-28", "2026-07-13", "3,578 bills unchanged from the first scrape until 07-14 "
          "(found by the replay, confirmed from 11-27 by the review)", "plan doc, review of the profiles step (2026-11-26)"),
    # Third wave (added 2026-11-26 overnight, before its held-out scoring, from
    # /Volumes/govbot-data/scratch/claude-review/notes-by-state.md, which cites error-tracking.md,
    # 2026-07-14-recovery-summary.md and working-out-of-session.md): the Dec 2025 freeze.
    Event("ak", "unchanged", "2025-12-14", "2026-07-13", "stuck at 514 bills while green (the Dec 2025 freeze)",
          "notes-by-state § AK (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("in", "unchanged", "2025-12-14", "2026-07-13", "stuck at 40 bills while green (the Dec 2025 freeze)",
          "notes-by-state § IN (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("mi", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~2,360 bills while green (the Dec 2025 freeze)",
          "notes-by-state § MI (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("ne", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~1,037 bills while green (the Dec 2025 freeze)",
          "notes-by-state § NE (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("ny", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~9,584 bills while green (the Dec 2025 freeze)",
          "notes-by-state § NY (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("oh", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~1,538 bills while green (the Dec 2025 freeze)",
          "notes-by-state § OH (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("sc", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~3,051 bills while green (the Dec 2025 freeze)",
          "notes-by-state § SC (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("usa", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~8,250 bills while green (the Dec 2025 freeze)",
          "notes-by-state § USA (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("vt", "unchanged", "2025-12-14", "2026-07-13", "stuck at 898 bills while green (the Dec 2025 freeze)",
          "notes-by-state § VT (error-tracking.md / 2026-07-14-recovery-summary.md)"),
    Event("wa", "unchanged", "2026-07-24", "2026-07-25", "frozen since 07-24 04:06, silently 'success' (out of session)",
          "notes-by-state § WA (working-out-of-session.md)"),
    # Added during scoring (2026-11-26, step 5): WV is in the recovery summary's table of states
    # frozen since 2025-12-14 (~2,709 -> 5,950 files), missed when the third-wave events were added.
    Event("wv", "unchanged", "2025-12-14", "2026-07-13", "stuck at ~2,709 files while green (the Dec 2025 freeze; "
          "Azure IP block)", "2026-07-14-recovery-summary.md; error-tracking.md § WV"),
    # Confirmed by Tamara on 2026-11-26 (review of the overnight work, decision 1): freezes the
    # held-out replay found and the notes never recorded. Each window runs from the day after
    # the last scrape with anything new to the day before the next one; in session there were
    # scrapes, but no new bill, action or vote.
    Event("wi", "unchanged", "2025-11-27", "2026-05-13", "stuck at 1,624 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("wi", "unchanged", "2026-05-15", "2026-07-14", "stuck at ~1,626 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("wi", "unchanged", "2026-07-16", "2026-08-19", "stuck at 2,751 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("md", "unchanged", "2026-01-14", "2026-07-14", "stuck at 531 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("ks", "unchanged", "2025-11-27", "2026-05-08", "stuck at 781 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("id", "unchanged", "2026-01-14", "2026-07-14", "stuck at 1 bill: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("sd", "unchanged", "2025-12-31", "2026-07-01", "stuck at 41 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("ms", "unchanged", "2026-01-08", "2026-02-03", "stuck at 18 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("ms", "unchanged", "2026-02-05", "2026-07-14", "stuck at 2,991 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("wa", "unchanged", "2025-11-27", "2026-04-21", "stuck at 2,075 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("mn", "unchanged", "2025-11-27", "2026-03-11", "stuck at 6,958 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("mn", "unchanged", "2026-03-29", "2026-07-14", "stuck at 9,808 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("or", "unchanged", "2026-01-31", "2026-07-14", "stuck at 264 bills: scraped, nothing new (unrecorded freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("ma", "no_new_bills", "2025-11-28", "2026-07-01", "exactly 8,975 bills; no new bills, actions still came",
          "Progress, first wave, finding 2"),
    # Empty: committed scrapes with no readable bill.
    Event("ar", "empty_scrape", "2026-03-13", "2026-07-13", "0 bill files in 119 scrapes", "plan section 1; Progress"),
    Event("il", "empty_scrape", "2026-07-03", "2026-07-03", "a 0-bill scrape committed as green", "il.md"),
    Event("il", "empty_scrape", "2026-07-13", "2026-07-13", "a 0-bill scrape committed as green", "il.md"),
    Event("ga", "empty_scrape", "2026-07-21", "2026-07-26", "every bill file had conflict markers", "notes-by-state § GA"),
    Event("nh", "empty_scrape", "2026-06-26", "2026-06-27", "4 scrapes with 0 bill files", "Progress, first wave (NH report)"),
    Event("nh", "empty_scrape", "2026-07-03", "2026-07-03", "a scrape with 0 bill files", "Progress, first wave (NH report)"),
    Event("ma", "empty_scrape", "2026-06-29", "2026-06-30", "2 scrapes with 0 bill files", "Progress, first wave (MA report)"),
    # A field emptied on most bills at once (option C guard (c)).
    Event("il", "field_loss", "2026-07-13", "2026-09-30", "abstracts on 8,648 of 8,648 bills, never back", "il.md"),
    Event("ky", "field_loss", "2026-08-20", "2026-09-30", "sponsorships on 1,707 of 1,707 bills, never back", "ky.md"),
    Event("nh", "field_loss", "2025-12-25", "2025-12-25", "sponsorships 1,143 of 1,143", "bill-skip-option-c.md"),
    Event("nh", "field_loss", "2025-12-30", "2025-12-30", "sponsorships 1,143 of 1,143", "bill-skip-option-c.md"),
    Event("nh", "field_loss", "2026-01-28", "2026-09-30", "documents 33 of 33, never back", "bill-skip-option-c.md; Progress"),
    Event("ks", "field_loss", "2026-05-09", "2026-09-30", "extras and other_titles on 781 of 781 bills, never back "
          "(the scrape that ended KS's freeze)", "history scanner, confirmed by Tamara 2026-11-26"),
    Event("nh", "field_loss", "2026-08-21", "2026-08-21", "versions 1,126 of 1,155", "bill-skip-option-c.md"),
    # Roll calls saved broken.
    Event("tn", "broken_votes", "2026-06-26", "2026-09-30", "6,787 roll calls emptied over 63 nights, 5,839 on 07-02", "tn.md"),
    Event("nd", "broken_votes", "2025-12-30", "2025-12-30", "error page as a voter, 1,137 votes", "nd.md"),
    Event("nd", "broken_votes", "2026-04-22", "2026-04-22", "error page as a voter, 1,149 votes", "nd.md"),
    Event("nd", "broken_votes", "2026-04-30", "2026-04-30", "error page as a voter, 1,166 votes", "nd.md"),
    Event("nd", "broken_votes", "2026-06-20", "2026-06-20", "error page as a voter, 1,166 votes", "nd.md"),
    Event("nd", "broken_votes", "2026-06-24", "2026-06-24", "error page as a voter, 1,166 votes", "nd.md"),
    Event("nd", "broken_votes", "2026-08-11", "2026-08-11", "error page as a voter, 1,166 votes", "nd.md; Progress"),
    Event("nd", "broken_votes", "2026-08-29", "2026-08-29", "'Proxy Error' as a voter, 1,166 votes", "nd.md"),
    Event("nd", "broken_votes", "2026-09-19", "2026-09-19", "'Proxy Error' as a voter, 15 votes", "nd.md"),
    # FL: windows where its raw history misleads (see CAVEATS["fl"]). No check is expected to
    # catch them (check ""), but they're left out when FL's normal is measured.
    Event("fl", "", "2025-11-27", "2026-08-07", "House committee votes missing on bot-blocked bills (987 of 988 votes "
          "missing from their bill's last scrape, 452 bills)", "fl.md § 2026-08-07; Progress, profiles step"),
    Event("fl", "", "2026-04-25", "2026-07-24", "regular session (1,897 bills) out of the scrape; only 2026D scraped",
          "Progress, first wave, finding 3"),
    Event("fl", "", "2026-07-21", "2026-08-07", "partial runs auto-saved up to 40 times a day; up to 13,807 files "
          "for 1,902 bills", "fl.md § 2026-07-25/26; Progress, profiles step"),
    Event("fl", "", "2026-07-23", "2026-07-23", "change point: the scraper became the custom fl-fix-test image "
          "(streaming, timeouts, single-bill resilience)", "fl.md § 2026-07-23/24"),
    # Maintenance commits under _data/ that are not scrapes.
    Event("ct", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log"),
    Event("pa", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log"),
    Event("mo", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log; confirmed by Tamara 2026-11-26"),
    Event("mt", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log; confirmed by Tamara 2026-11-26"),
    Event("oh", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log; confirmed by Tamara 2026-11-26"),
    Event("pr", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log; confirmed by Tamara 2026-11-26"),
    Event("usa", "", "2026-07-21", "2026-07-21", "manual commit 'clear duplicate-accumulated scrape data', not a scrape",
          "raw git log; confirmed by Tamara 2026-11-26"),
    # Data reshaped wrongly.
    Event("tn", "chamber_swap", "2026-06-26", "2026-07-02", "Senate bills' actions saved under the House", "review of the first wave, correction 2"),
]


# How a state's raw history misleads: what the scanner reads, and what was really going on.
# profiles.py copies these into the state's profile, so whoever reads its numbers sees them.
# Keep in step with the state file (tamara-notes/state-specific/<st>.md).
CAVEATS = {
    "gu": [
        "No bill has any actions or documents (plan section 1), so 'nothing new' is GU's normal and the "
        "`unchanged` check fires all the time. GU needs another freshness signal (new bills, versions).",
    ],
    "vi": [
        "Since 2025-12-07 its 'Scrape data for vi' commits change only .windycivi/warning_history.json, "
        "never _data/vi: no data for ten months, behind commits that look like scrapes. Count only "
        "commits that touch _data/vi.",
    ],
    "fl": [  # Tamara's rules for reading FL (2026-11-26) plus what the scan shows; evidence in fl.md
        "A scrape that looks complete isn't. flhouse.gov's bot detection returns a 'Request Rejected' "
        "page with HTTP 200, so a blocked page looks like a good one, and blocked runs finish green: "
        "1,480 of 1,902 bills (78%) blocked on 08-07, 98.5% on 07-26. Treat every FL scrape as a "
        "sample, not the truth: judge a bill by the best version ever seen, not the last one.",
        "A block costs one thing: House committee roll calls. Title, sponsors, actions and floor votes "
        "come from flsenate.gov and survive. House committee votes come only from flhouse.gov, so a "
        "blocked rescrape deletes one captured earlier (HB 755: ~07-25, gone 08-07). A missing House "
        "committee vote is a block, not news, and the bill's actions still say the committee voted.",
        "`extras.scrape_warnings` (from 07-24) marks a bill whose flhouse.gov pages were skipped. That "
        "field going away means the bill was NOT blocked that night: its 'loss' is good news.",
        "The scraper changed on 07-23: before, it held the whole session in memory and often saved zero "
        "bills or crashed on one bad bill; from 07-23 it's our custom image fl-fix-test (streaming, "
        "timeouts, single-bill resilience). Don't compare across 07-23 as if nothing changed.",
        "Count distinct bills, never files. Stale copies pile up between full runs (3,123 files for "
        "1,878 bills, then 5,330, up to 11 copies of one bill; 13,807 files for 1,902 on 08-07); each "
        "full run cleans them up.",
        "Commits in July-August are not nights. Partial runs auto-saved up to 40 times a day (07-21 to "
        "08-07), so per-scrape bills new/gone and 'identical' runs describe a run in progress.",
        "Known events, not findings: 07-21 a short 'successful' run overwrote a longer run's data; the "
        "regular session ended 03-13; the regular session left the scrape 04-25 to 07-24 (the scrape "
        "followed the 2026D special session); SPB bills vanish when filed as numbered SBs (normal); "
        "`subject` holds the junk values 'subject index' and '(vetoed)'.",
        "The history ends on 08-07 on purpose: the 09-27 to 09-29 runs were cancelled waiting for a "
        "self-hosted runner. 08-08 to the pause is an outage, not data loss.",
        "'Blocked or just slow?' has been asked three times; both happened. Bot detection is the usual "
        "case; a real IP block happened on 07-21. Don't re-derive it.",
        "Not nightly even in session: 5 gaps of 3-12 days between scrapes during the 2026 session.",
    ],
}


def events_for(state: str, check: Optional[str] = None) -> list[Event]:
    return [e for e in EVENTS if e.state == state and (check is None or e.check == check)]
