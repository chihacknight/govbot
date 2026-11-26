#!/usr/bin/env python3
"""Acceptance test on the real history: does the database reproduce what we already know?

Plan section 3, "Checks against what we already know": a mismatch means the scanner is wrong,
not the notes. Each state's checks are listed below with where the number comes from; add a
state's checks before trusting its scan. Optionally compares the per-field losses with
`field_loss.py`'s output (the option C measurement), row for row.

usage:
  python3 check_known.py [--db history.sqlite] [--field-loss-dir <dir with field_loss_<st>.tsv>] wy ky ar
Exit status 1 if any check fails. "info" lines show evidence for a claim with no exact number.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path("/Volumes/govbot-data/scratch/history-analysis/history.sqlite")
FIELD_LOSS_FIELDS = ("sponsorships", "actions", "versions", "documents", "abstracts", "other_titles",
                     "subject", "sources", "title")


def one(con, sql, *args):
    return con.execute(sql, args).fetchone()


def check_ar(con):
    # Plan section 1: 0 bill files in 119 committed scrapes from 03-13 to 07-12, then 2 bills
    # (2026S1); 1,928 bills in session 2025, in the July archive but not the data repo.
    n, first, last = one(con, "SELECT COUNT(*), MIN(committed_at), MAX(committed_at) FROM scrapes "
                              "WHERE state = 'ar' AND bill_files = 0")
    yield "119 scrapes with 0 bill files", n == 119, f"{n}, {first[:10]} to {last[:10]}"
    s = one(con, "SELECT raw_bills, data_repo_bills, archive_bills FROM sessions WHERE state = 'ar' AND session = '2025'")
    yield "session 2025: 1,928 raw, 0 in data repo, 1,928 in archive", s == (1928, 0, 1928), str(s)
    s = one(con, "SELECT raw_bills, data_repo_bills FROM sessions WHERE state = 'ar' AND session = '2026S1'")
    yield "session 2026S1: 2 bills", s == (2, 2), str(s)


def check_ky(con):
    # tamara-notes/state-specific/ky.md: sponsors gone from 1,707 of 1,707 bills on 08-20, never back.
    r = one(con, "SELECT substr(committed_at, 1, 10), lost, had, lost_back FROM scrape_fields "
                 "WHERE state = 'ky' AND field = 'sponsorships' AND lost >= 20")
    yield "sponsorships lost on 1,707 of 1,707 bills on 08-20, none back", r == ("2026-08-20", 1707, 1707, 0), str(r)
    r = one(con, "SELECT share_latest FROM fields WHERE state = 'ky' AND field = 'sponsorships'")
    yield "no sponsors in the latest scrape", r is not None and r[0] == 0, str(r)
    r = one(con, "SELECT changed, ws_only, examples FROM scrape_fields WHERE state = 'ky' AND field = 'abstracts' "
                 "AND ws_only > 0")
    yield "whitespace-only abstract change (SB4)", r is not None and "SB4" in r[2], str(r)


def check_wy(con):
    # archived_docs/openstates-responses.md § WY (2026-07-02): the 2026 budget session had 23
    # bills, missing HB0001, SF0001, SF0002 (the API left out enrolled/inactive bills).
    # notes-by-state.md: 556 bills from 2025 in raw, not in the data repo.
    rows = con.execute("SELECT identifier, first_at FROM bills WHERE state = 'wy' AND session = '2026' "
                       "AND identifier IN ('HB0001', 'SF0001', 'SF0002')").fetchall()
    first = {i: f[:10] for i, f in rows}
    yield "budget bills first seen only in July 2026", len(first) == 3 and all(f >= "2026-07" for f in first.values()), str(first)
    n = one(con, "SELECT MAX(bills) FROM scrapes WHERE state = 'wy' AND committed_at BETWEEN '2026-01' AND '2026-07-01'")[0]
    yield "23 bills in the 2026 session before July", n == 23, str(n)
    s = one(con, "SELECT raw_bills, data_repo_bills, archive_bills FROM sessions WHERE state = 'wy' AND session = '2025'")
    yield "session 2025: 556 raw, 0 in data repo, in archive", s == (556, 0, 556), str(s)


# From the JSONL log conversion's "Results by repo" table
# (tamara-notes/processes/workstreams/shared-docs/jsonl-log-conversion-results.md), which replayed
# the same raw histories: scrapes, distinct votes in the sessions the data repo has, raw bills with
# no folder in the data repo (per session), and conflict-marker files (count, night).
CONVERSION = {
    "ar": dict(scrapes=256, votes=0, no_folder={"2025": 1928}),
    "ky": dict(scrapes=290, votes=886, no_folder={"2025RS": 1441}),
    "wy": dict(scrapes=311, votes=1258, no_folder={"2025": 556}),
    # votes_split: measured from the converted logs, the same votes keyed the scanner's way
    # (bill + roll-call id + date + motion + chamber): DE 2,060 of 2,063 ids, NH 403 of 636.
    "de": dict(scrapes=291, votes=2063, votes_split=3, no_folder={}),
    "nh": dict(scrapes=148, votes=636, votes_split=233, no_folder={"2025": 1072, "2026": 7}),
    "fl": dict(scrapes=351, votes=2709, no_folder={"2026": 19, "2026D": 6}),
    "tx": dict(scrapes=41, votes=0, no_folder={"891": 592, "89R": 11503}, conflict=(582, "2026-06-26")),
    "nc": dict(scrapes=295, votes=869, votes_split=1, no_folder={}),  # 868 keyed the scanner's way
    "nd": dict(scrapes=288, votes=2180, votes_split=1, no_folder={}),  # 2,179
    "ga": dict(scrapes=280, votes=280, no_folder={"2025_26": 5480}, conflict=(914, "2026-07-21")),
    "ma": dict(scrapes=439, votes=0, no_folder={"194th": 81}),
    "tn": dict(scrapes=215, votes=19062, no_folder={}),
    "il": dict(scrapes=455, votes=9842, votes_split=132, no_folder={}),  # 9,710 keyed the scanner's way
    "ca": dict(scrapes=302, votes=21566, votes_split=35, no_folder={}),  # 21,531
    # Third wave (added 2026-11-26 overnight, same table). votes_split is measured from the converted
    # logs before scoring (log ids vs the scanner's key), as for the first wave.
    "ak": dict(scrapes=330, votes=1109, no_folder={}),
    "al": dict(scrapes=256, votes=0, no_folder={}),
    "ia": dict(scrapes=363, votes=0, no_folder={}),
    "id": dict(scrapes=297, votes=853, no_folder={'2025': 790}),
    "in": dict(scrapes=287, votes=690, votes_split=1, no_folder={}),
    "ks": dict(scrapes=295, votes=0, no_folder={}),
    "md": dict(scrapes=253, votes=0, no_folder={'2025': 2617}),
    "me": dict(scrapes=414, votes=1576, votes_split=10, no_folder={}),
    "mi": dict(scrapes=562, votes=1628, votes_split=345, no_folder={}),
    "mn": dict(scrapes=298, votes=245, no_folder={'2025-2026': 2, '2025s1': 48}),
    "mo": dict(scrapes=419, votes=1491, no_folder={'2025S2': 15, '2026': 47}),
    "ms": dict(scrapes=274, votes=1828, no_folder={'20251E': 106}),
    # MT: 31 roll calls with their own roll-call number but the same time, motion, result, counts and
    # voters as another on the bill (SB 155 has 10 copies of one 02-06 committee vote, -828 ... -1220);
    # the log gives them one id, the scanner counts each (`votes_merged`).
    "mt": dict(scrapes=401, votes=8730, votes_merged=31, no_folder={}),
    "ne": dict(scrapes=449, votes=1774, votes_split=3, no_folder={}),
    "nv": dict(scrapes=291, votes=33, no_folder={}),
    "ny": dict(scrapes=573, votes=10850, votes_split=297, no_folder={}),
    "oh": dict(scrapes=516, votes=1104, votes_split=1, no_folder={}, conflict=(464, '2026-07-21')),
    "ok": dict(scrapes=278, votes=8766, votes_split=19, no_folder={'2025': 3257, '2026': 5}),
    "or": dict(scrapes=291, votes=0, no_folder={'2025S1': 3}),
    # PR: its data repo is not on the SSD (converted on a case-sensitive disk image: two file names
    # differ only in case), so the scanner can't compare folders; the conversion found 1.
    "pr": dict(scrapes=443, votes=0, no_folder={'2025-2028': 1}, no_data_repo=True),
    "ri": dict(scrapes=276, votes=1092, votes_split=50, no_folder={'2025': 2595, '2026': 6}),
    "sc": dict(scrapes=357, votes=2051, votes_split=49, no_folder={}),
    "sd": dict(scrapes=300, votes=1511, votes_split=2, no_folder={'2025s': 2}),
    # USA: 174 of these votes name their bill another way ("SJRes 5", "HJ RES 1" for SJRES 5,
    # HJRES 1); the scanner matches identifiers without case, spaces or punctuation (scan.norm_ident).
    "usa": dict(scrapes=688, votes=852, no_folder={}),
    "ut": dict(scrapes=261, votes=1917, no_folder={'2025S1': 18}),
    # VT: H 740's 05-19 Senate roll calls #157 and #161 (both passed 17-13) got one log id, so #161
    # is not in vote_event_logs.jsonl: a real loss in the logs, found here (`votes_merged`).
    "vt": dict(scrapes=405, votes=148, votes_merged=1, no_folder={}),
    "wa": dict(scrapes=420, votes=2302, no_folder={}),
    "wi": dict(scrapes=330, votes=2298, votes_split=1, no_folder={}),
    "wv": dict(scrapes=492, votes=1146, votes_split=3, no_folder={'2025': 2709}, conflict=(14, '2026-07-14')),
}


def check_conversion(con, st):
    c = CONVERSION[st]
    n = one(con, "SELECT COUNT(*) FROM scrapes WHERE state = ?", st)[0]
    yield f"{c['scrapes']} scrapes", n == c["scrapes"], str(n)
    # Votes in the sessions the data repo has (the conversion only replayed those).
    # Votes on the bills the data repo has (the conversion only replayed those). Its count is of
    # log ids, which split a no-roll-call-number vote whose counts changed (option C item 4), so
    # where that happens it is higher; `votes_split` gives that state's known difference.
    n = one(con, "SELECT COALESCE(SUM(votes_ever), 0) FROM bills WHERE state = ? AND in_data_repo = 1", st)[0]
    want = c["votes"] - c.get("votes_split", 0) + c.get("votes_merged", 0)
    yield f"{want:,} distinct votes on the data repo's bills", n == want, f"{n:,}"
    if c.get("no_data_repo"):
        yield f"info: no data repo on the SSD; the conversion found {c['no_folder']} with no folder", None, "not compared"
        return
    got = {s: n for s, n in con.execute(
        "SELECT session, COUNT(*) FROM bills WHERE state = ? AND in_data_repo = 0 GROUP BY session", (st,))}
    yield f"raw bills with no folder in the data repo: {c['no_folder'] or 'none'}", got == c["no_folder"], str(got)
    if "conflict" in c:
        n, night = c["conflict"]
        got = con.execute("SELECT substr(committed_at, 1, 10), COUNT(*) FROM bad_files WHERE state = ? "
                          "AND problem = 'conflict' GROUP BY 1", (st,)).fetchall()
        yield f"{n} files with conflict markers on {night}", [tuple(r) for r in got] == [(night, n)], str(got)


def check_de(con):
    # Baseline (plan section 1): no known problems. The SB315 vote flip (pass -> fail -> pass,
    # jsonl-log-conversion-results.md) needs a per-vote table, which the scanner doesn't keep.
    n = one(con, "SELECT COUNT(*) FROM scrapes WHERE state = 'de' AND bills = 0")[0]
    yield "no scrape with 0 bills", n == 0, str(n)
    r = one(con, "SELECT content_changes, votes_ever FROM bills WHERE state = 'de' AND identifier = 'SB 315' "
                 "ORDER BY last_at DESC")
    yield "info: SB 315 (its vote went pass -> fail -> pass)", None, f"content changes, votes: {r}"


def check_nh(con):
    # bill-skip-option-c.md § Review: sponsors lost on 1,143 of 1,143 bills on 12-25 and 12-30,
    # documents 33/33 on 01-28, versions 1,126/1,155 on 08-21; all came back.
    want = {("2025-12-25", "sponsorships", 1143, 1143), ("2025-12-30", "sponsorships", 1143, 1143),
            ("2026-01-28", "documents", 33, 33), ("2026-08-21", "versions", 1126, 1155)}
    got = {(r[0], r[1], r[2], r[3]): r[4] for r in con.execute(
        "SELECT substr(committed_at, 1, 10), field, lost, had, lost_back FROM scrape_fields WHERE state = 'nh' "
        "AND field IN ('sponsorships', 'documents', 'versions') AND lost >= 20")}
    yield "the four known field losses", want <= set(got), str(sorted(got))
    # Came back: sponsors on every bill still scraped (12-30: HB1545 was never scraped again);
    # versions on all. Documents never came back: no NH bill has any after 01-28 (the notes said
    # all recovered; corrected 2026-11-25).
    back = {("2025-12-25", "sponsorships"): 1143, ("2025-12-30", "sponsorships"): 1142,
            ("2026-08-21", "versions"): 1126, ("2026-01-28", "documents"): 0}
    yield "came back: sponsors and versions yes, documents no", \
        all(got.get(k) == back[k[:2]] for k in want), str({k[:2]: got.get(k) for k in want})
    # 2026-07-14-recovery-summary.md: a rate-limited run wiped 436 real files (restored).
    rows = con.execute("SELECT substr(committed_at, 1, 16), bill_files, bills, bills_gone FROM scrapes WHERE state = 'nh' "
                       "AND committed_at BETWEEN '2026-07-12' AND '2026-07-16' ORDER BY idx").fetchall()
    yield "info: the 07-14 run that wiped 436 files", None, str([tuple(r) for r in rows])


def check_fl(con):
    # fl.md § 2026-08-07: HB 755's House committee vote, captured ~07-25, gone on 08-07 (the last
    # FL scrape); 1,480 of 1,902 bills hit the flhouse.gov block in that run.
    r = one(con, "SELECT identifier, votes_ever, votes_gone_for_good, last_at FROM bills WHERE state = 'fl' "
                 "AND session = '2026' AND replace(identifier, ' ', '') = 'HB755'")
    yield "HB 755: a vote seen earlier is missing from its last scrape", r is not None and r[2] >= 1, str(r)
    r = one(con, "SELECT substr(committed_at, 1, 10), votes, votes_gone FROM scrapes WHERE state = 'fl' ORDER BY idx DESC")
    yield "the last scrape is 08-07 and lost votes", r[0] == "2026-08-07" and r[2] > 0, str(r)
    # fl.md / not-working.md: duplicate bloat 07-25/26, 3,123 files for 1,878 bills, later 5,330.
    rows = con.execute("SELECT substr(committed_at, 1, 10), bill_files, bills FROM scrapes WHERE state = 'fl' "
                       "AND bill_files IN (3123, 5330)").fetchall()
    yield "duplicate bloat: 3,123 and 5,330 files for 1,878 bills", {(r[1], r[2]) for r in rows} == {(3123, 1878), (5330, 1878)}, \
        str([tuple(r) for r in rows])


def check_tx(con):
    # Plan section 0: 89R (11,503) and 891 (592) are in the July archive.
    rows = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT session, raw_bills, archive_bills FROM sessions WHERE state = 'tx' AND session IN ('89R', '891')")}
    yield "89R 11,503 and 891 592, raw and July archive", rows == {"89R": (11503, 11503), "891": (592, 592)}, str(rows)


def check_nc(con):
    # notes-by-state.md § NC (scraper-health.md): stuck at 1,794 bills 2025-12-14 to 2026-07-14
    # while green (never `runner: self-hosted`); 07-14: 2,334 bills, matching the live feed.
    r = one(con, "SELECT MIN(bills), MAX(bills), COUNT(*), SUM(identical_content) FROM scrapes WHERE state = 'nc' "
                 "AND committed_at BETWEEN '2025-12-15' AND '2026-07-13'")
    yield "1,794 bills in every scrape 12-15 to 07-13", r[0] == r[1] == 1794, f"min, max, scrapes, unchanged: {r}"
    r = one(con, "SELECT substr(committed_at, 1, 10), bills FROM scrapes WHERE state = 'nc' AND bills > 1794 ORDER BY idx")
    yield "first scrape past 1,794: 2,334 bills on 07-14", r == ("2026-07-14", 2334), str(r)


def check_nd(con):
    # nd.md: votes with an error page as a voter, by night ("Service Unavailable" x6, then "Proxy
    # Error" x2), counted in the converted logs by the night the bad version was first seen. The
    # scanner counts the votes broken in each scrape; they differ on 08-11 only: 1,166 broken,
    # but 1,132 of those bad versions are identical to 12-30's, so the logs count 34 new ones
    # (checked against the raw files 2026-11-25).
    want = {"2025-12-30": 1137, "2026-04-22": 1149, "2026-04-30": 1166, "2026-06-20": 1166, "2026-06-24": 1166,
            "2026-08-11": 1166, "2026-08-29": 1166, "2026-09-19": 15}
    got = dict(con.execute("SELECT substr(committed_at, 1, 10), votes_error_voters FROM scrapes WHERE state = 'nd' "
                           "AND votes_error_voters > 0").fetchall())
    yield "error-page voters on the 8 known nights, same counts", got == want, str(got)


def check_ga(con):
    # notes-by-state.md § GA (critical-merge-conflict-corruption.md): every bill file had conflict
    # markers for 5 days from 07-21 (commit 0ea65a5e) until the next run replaced them.
    rows = con.execute("SELECT substr(committed_at, 1, 10), sha, bill_files, bills, bad_conflict FROM scrapes "
                       "WHERE state = 'ga' AND bad_conflict > 0 ORDER BY idx").fetchall()
    yield "info: scrapes with conflict markers", None, str([(r[0], r[1][:8], r[2], r[3], r[4]) for r in rows])
    yield "the first is 0ea65a5e on 07-21", bool(rows) and rows[0][1].startswith("0ea65a5e") and rows[0][0] == "2026-07-21", \
        str(rows[0][:2] if rows else None)


def check_ma(con):
    # ma.md: a "Server Error" warning silently dropped ~210-218 bills per run, 2026-07-01 to 08-07.
    rows = [r[0] for r in con.execute("SELECT bills_gone FROM scrapes WHERE state = 'ma' AND committed_at BETWEEN "
                                      "'2026-07-01' AND '2026-08-08' AND bills > 0 ORDER BY bills_gone")]
    med = rows[len(rows) // 2] if rows else None
    yield "info: bills gone per scrape 07-01 to 08-07 (median; the notes say ~210 dropped per run)", None, \
        f"median {med}, {len(rows)} scrapes"
    r = one(con, "SELECT MAX(dup_ratio) FROM scrapes WHERE state = 'ma'")
    yield "info: worst duplicate ratio (the notes say 4.5x)", None, str(r[0])
    rows = con.execute("SELECT session, identifier FROM bills WHERE state = 'ma' AND gone_for_good AND session_continued "
                       "AND last_at BETWEEN '2026-07-26' AND '2026-07-28'").fetchall()
    yield "info: bills last seen 07-26/27, never back (the notes: 3 dropped on 07-27)", None, str(rows)


def check_tn(con):
    # tn.md: 6,787 roll calls went from names to empty over 63 nights, 5,839 of them on 07-02.
    r = one(con, "SELECT SUM(votes_emptied), COUNT(DISTINCT substr(committed_at, 1, 10)) FROM scrapes "
                 "WHERE state = 'tn' AND votes_emptied > 0")
    yield "6,787 roll calls emptied, over 63 nights", tuple(r) == (6787, 63), str(r)
    r = one(con, "SELECT SUM(votes_emptied) FROM scrapes WHERE state = 'tn' AND committed_at LIKE '2026-07-02%'")
    yield "5,839 of them on 07-02", r[0] == 5839, str(r[0])
    # Plan section 1: only 37 of ~5,400 bills before July's IP-block fix.
    r = one(con, "SELECT MAX(bills) FROM scrapes WHERE state = 'tn' AND committed_at < '2026-07-01'")
    yield "info: most bills in a scrape before July (the notes: 37)", None, str(r[0])


def check_il(con):
    # il.md: the synopsis (`abstracts`) gone from 8,648 of 8,648 bills on 07-13 (22:55 local), never back.
    r = one(con, "SELECT committed_at, lost, had, lost_back FROM scrape_fields WHERE state = 'il' AND field = 'abstracts' "
                 "AND lost >= 20")
    yield "abstracts lost on 8,648 of 8,648 bills, none back", r is not None and tuple(r[1:]) == (8648, 8648, 0), str(r)
    # il.md: two scrapes with 0 bill files committed as green runs, 07-03 04:46 and 07-13 21:00.
    rows = [r[0] for r in con.execute("SELECT committed_at FROM scrapes WHERE state = 'il' AND bill_files = 0")]
    yield "two scrapes with 0 bill files, on 07-03 and 07-13/14", len(rows) == 2, str(rows)
    # notes-by-state.md § IL (error-tracking.md): stuck at ~2,944 bills 12-14 to 07-14.
    r = one(con, "SELECT MIN(bills), MAX(bills), SUM(identical_content), COUNT(*) FROM scrapes WHERE state = 'il' "
                 "AND committed_at BETWEEN '2025-12-15' AND '2026-07-01' AND bills > 0")
    yield "info: bills 12-15 to 07-01 (min, max, unchanged scrapes, scrapes; the notes: ~2,944)", None, str(r)
    # bill-skip-option-c.md: "Dan Ugaste" -> "Daniel J. Ugaste" on 716 sponsorships.
    rows = [r[0] for r in con.execute("SELECT substr(committed_at, 1, 10) || ' ' || json_extract(examples, '$.sponsor_rename_top') "
                                      "FROM scrapes WHERE state = 'il' AND examples LIKE '%Ugaste%'")]
    yield "info: the Ugaste rename (the notes: 716 sponsorships)", None, str(rows)


def check_ca(con):
    # jsonl-log-conversion-results.md: 5,115 reworded action lines (5.5%); plan section 1: 5,088.
    r = one(con, "SELECT SUM(actions_reworded), SUM(actions_ws_only) FROM scrapes WHERE state = 'ca'")
    yield "info: reworded and whitespace-only actions (the notes: 5,088 / 5,115 reworded lines)", None, str(r)


CHECKS = {"ar": check_ar, "ky": check_ky, "wy": check_wy, "de": check_de, "nh": check_nh, "fl": check_fl,
          "tx": check_tx, "nc": check_nc, "nd": check_nd, "ga": check_ga, "ma": check_ma, "tn": check_tn,
          "il": check_il, "ca": check_ca}


def check_field_loss(con, state, tsv: Path):
    """Every field_loss.py row (night, field, lost, had) has the same row in scrape_fields, and
    the other way round. field_loss.py dates a night by the commit's own timezone, the scanner
    by UTC; the self-hosted runner commits in US Central time, so a night matches its UTC date
    or the date 5 or 6 hours earlier."""
    theirs = set()
    for line in tsv.read_text().splitlines():
        night, field, lost, had, _ = line.split("\t")
        theirs.add((night, field, int(lost), int(had)))
    ours = []
    for at, field, lost, had in con.execute(
            "SELECT committed_at, field, lost, had FROM scrape_fields WHERE state = ? AND lost > 0 "
            f"AND field IN ({','.join('?' * len(FIELD_LOSS_FIELDS))})", (state, *FIELD_LOSS_FIELDS)):
        t = datetime.fromisoformat(at)
        nights = {(t - timedelta(hours=h)).date().isoformat() for h in (0, 5, 6)}
        ours.append((nights, field, lost, had))
    left = list(ours)
    only_theirs = []
    for night, field, lost, had in sorted(theirs):
        hit = next((o for o in left if night in o[0] and o[1:] == (field, lost, had)), None)
        if hit is None:
            only_theirs.append((night, field, lost, had))
        else:
            left.remove(hit)
    only_ours = [(min(o[0]),) + o[1:] for o in left]
    yield f"field_loss.py rows ({len(theirs)}) match", not only_theirs and not only_ours, \
        f"only field_loss: {only_theirs[:5]}; only scanner: {only_ours[:5]}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("states", nargs="+")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--field-loss-dir", type=Path)
    a = p.parse_args(argv)
    con = sqlite3.connect(str(a.db))
    failed = 0
    for st in a.states:
        st = st.lower()
        checks = list(CHECKS[st](con)) if st in CHECKS else []
        if st in CONVERSION:
            checks += list(check_conversion(con, st))
        tsv = a.field_loss_dir / f"field_loss_{st}.tsv" if a.field_loss_dir else None
        if tsv and tsv.exists():
            checks += list(check_field_loss(con, st, tsv))
        if not checks:
            print(f"{st}: no known numbers to check yet")
        for name, ok, got in checks:  # ok None: shown for a person to judge, not pass/fail
            failed += ok is False
            print(f"{st}: {'info' if ok is None else 'ok  ' if ok else 'FAIL'} {name}  [{got}]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
