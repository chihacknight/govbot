#!/usr/bin/env python3
"""Replay one state's whole raw scrape history into the history-analysis database.

Plan: tamara-notes/processes/workstreams/shared-docs/history-analysis-plan.md (sections 3-5).
This step only measures; it finds patterns for the state auditor. It never fixes or restores.

A scrape is one commit in the raw scraper repo (<raw-root>/<st>-legislation) that touches
_data/<st>/, dated by its commit time (the time the logs use as first_seen). Scrapes are read
oldest to newest. Raw file names are random per scrape, and every bill file carries a fresh
`scraped_at` and `_id`, so files are compared by a hash of their content with those left out,
never by name or blob id. A blob seen in the previous scrape is not parsed again.

Everything read is read-only: `git ls-tree` and `git cat-file --batch`, never a checkout or
fetch. The raw repos, the data repos (<data-root>/<st>-legislation) and the govbot-archive
clones (<archive-root>/<st>-legislation and <st>-legislation-pre-rebuild-2026-07-21) are only
read; the data and archive repos only for their per-session bill counts (Table 3).

Re-scanning a state replaces all of its rows in one transaction, so the database contents are
the same on every run (the `runs` row records when and from which commits).

usage:
  python3 scan.py wy ky ar                       # scan these states, then write their reports
  python3 scan.py --jobs 4 ca de il ky           # four at a time (about 1.5 GB of memory each)
  python3 scan.py --db /tmp/x.sqlite --raw-root ... --data-root ... --archive-root ... wy

Standard library only, plus git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SSD = Path("/Volumes/govbot-data")
DEFAULT_RAW_ROOT = SSD / "raw-scrapers"
DEFAULT_DATA_ROOT = SSD / "govbot_data" / "full"
DEFAULT_ARCHIVE_ROOT = SSD / "govbot-archive"
DEFAULT_OUT = SSD / "scratch" / "history-analysis"
PRE_REBUILD_SUFFIX = "-pre-rebuild-2026-07-21"

# Keys that change on every scrape without the data changing.
VOLATILE = {"scraped_at", "_id"}
VOTE_VOLATILE = {"scraped_at", "_id", "bill"}  # `bill` points at the bill file's random _id
IDENTITY = {"legislative_session", "identifier"}

# The usual OpenStates bill shape. Any other top-level key is listed as unusual in `fields`.
STANDARD_BILL_KEYS = {
    "legislative_session", "identifier", "title", "from_organization", "classification", "subject",
    "abstracts", "other_titles", "other_identifiers", "actions", "sponsorships", "related_bills",
    "versions", "documents", "citations", "sources", "extras", "jurisdiction", "scraped_at", "_id",
}

# Voter names that are a failed page, not a person. ND saved "Service Unavailable" and
# "Proxy Error" (actions/format/utils/log_jsonl.py, _ND_ERROR_PAGES); the rest are the same kind.
ERROR_VOTER = re.compile(
    r"^(service unavailable|proxy error|bad gateway|gateway time-?out|internal server error|"
    r"forbidden|not found|access denied|request timeout|too many requests|error)\b"
    r"|\b(50[0-4]|40[34]|429)\b|<[a-z!/]",
    re.I,
)
# Seven or more: git lengthens the markers in some merges (TX's 2026-06-26 auto-merge has 8).
CONFLICT_MARKER = re.compile(rb"^(<{7,}|>{7,})( |$)", re.M)
EXAMPLES = 3  # example bills kept per measurement, as evidence


# ---------------------------------------------------------------------------
# The database. One CREATE TABLE per table, a comment per column (DBeaver users read these).
# Every table has a `state` column. Dates are UTC ISO strings as git gives them.
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS scrapes (          -- Table 1: one row per state and scrape (commit)
  state TEXT NOT NULL,                        -- jurisdiction code, e.g. 'ky'
  idx INTEGER NOT NULL,                       -- 0-based position in the state's history, oldest first
  sha TEXT NOT NULL,                          -- raw scraper repo commit
  committed_at TEXT NOT NULL,                 -- commit time (the logs' first_seen)
  subject TEXT,                               -- commit message subject
  gap_hours REAL,                             -- hours since the previous scrape
  files_total INTEGER,                        -- every file under _data/<st>/
  bill_files INTEGER,                         -- bill_*.json
  vote_files INTEGER,                         -- vote_event_*.json
  event_files INTEGER,                        -- event_*.json (counted, not analyzed)
  other_files INTEGER,                        -- jurisdiction_, organization_, anything else
  bills INTEGER,                              -- distinct readable bills (session + identifier)
  bills_by_session TEXT,                      -- JSON {session: distinct bills}
  dup_ratio REAL,                             -- readable bill files / distinct bills (1.0 = no duplicates)
  dup_bills_conflicting INTEGER,              -- bills with 2+ files whose contents differ
  bad_conflict INTEGER,                       -- files (any kind) with git conflict markers
  bad_invalid INTEGER,                        -- files that are not valid JSON (no markers)
  bad_empty INTEGER,                          -- empty or whitespace-only files
  bad_bills INTEGER,                          -- distinct bills only in unreadable files (identified by text search)
  identical_blobs INTEGER,                    -- 1 if the set of blobs equals the previous scrape's
  identical_content INTEGER,                  -- 1 if bill+vote contents (minus scraped_at/_id) equal the previous scrape's
  bills_new INTEGER,                          -- bills never seen before
  bills_returned INTEGER,                     -- bills seen before but not in the previous scrape
  bills_gone INTEGER,                         -- bills in the previous scrape, not in this one (unreadable ones not counted)
  bills_gone_back INTEGER,                    -- of bills_gone, how many appear again in a later scrape
  bills_changed INTEGER,                      -- bills present before whose content differs from their last-seen version
  actions INTEGER,                            -- actions across all bills in this scrape
  actions_new INTEGER,                        -- actions not in the bill's last-seen version (new bills: all), after pairing below
  actions_gone INTEGER,                       -- actions in the bill's last-seen version, missing now (bill still present), after pairing
  actions_reworded INTEGER,                   -- a gone and a new action paired on the same date + chamber (MT "First Reading" -> "1st Reading")
  actions_ws_only INTEGER,                    -- a gone and a new action that differ only in whitespace
  actions_chamber_swapped INTEGER,            -- a gone and a new action with the same date and words, another chamber (TN 07-02)
  votes INTEGER,                              -- distinct votes (bill + roll-call id + date + motion + chamber)
  votes_new INTEGER,                          -- votes never seen before
  votes_returned INTEGER,                     -- votes seen before but not in the previous scrape
  votes_changed INTEGER,                      -- votes whose content differs from their last-seen version
  votes_gone INTEGER,                         -- votes in the previous scrape, missing now, while their bill is present
  votes_rekeyed INTEGER,                      -- of votes_gone, those back now under another key on the same bill (same date + voters, or same date + motion)
  votes_empty INTEGER,                        -- votes with no voters listed
  votes_emptied INTEGER,                      -- votes with no voters now that had voters in their last-seen version (TN)
  votes_error_voters INTEGER,                 -- votes with a voter name that is error-page text (ND "Service Unavailable")
  votes_page_text INTEGER,                    -- votes with a voter name that looks like page text (> 60 chars, a line break, or 8+ words)
  votes_count_mismatch INTEGER,               -- votes whose yes, no or total count doesn't match the voter list (both present)
  votes_orphan INTEGER,                       -- votes whose bill is not in this scrape
  sponsors_renamed INTEGER,                   -- bills whose sponsor list kept its length and roles but a name changed
  examples TEXT,                              -- JSON {measurement: [up to 3 example bills or values]}, the evidence
  PRIMARY KEY (state, idx)
);
CREATE TABLE IF NOT EXISTS scrape_fields (    -- Table 1, per field: one row per state, scrape and field path
  state TEXT NOT NULL,
  idx INTEGER NOT NULL,                       -- scrapes.idx
  committed_at TEXT NOT NULL,                 -- scrapes.committed_at, repeated for easy queries
  field TEXT NOT NULL,                        -- 'sponsorships', 'versions[].links[].media_type', 'extras.BDR', 'versions.media=pdf', ...
  have INTEGER,                               -- bills in this scrape with the field filled
  had INTEGER,                                -- bills present now that had it filled in their last-seen version
  lost INTEGER,                               -- of `had`, bills where it is empty now
  lost_back INTEGER,                          -- of `lost`, bills where it is filled again in a later scrape
  gained INTEGER,                             -- bills present before where it is filled now but wasn't
  changed INTEGER,                            -- top-level fields only: filled before and now, content differs
  ws_only INTEGER,                            -- of `changed`, bills where only whitespace differs (KY)
  examples TEXT,                              -- JSON {"lost": [...], "changed": [...]} example bills
  PRIMARY KEY (state, idx, field)
);
CREATE TABLE IF NOT EXISTS bad_files (        -- Table 1, detail: every unreadable file
  state TEXT NOT NULL,
  idx INTEGER NOT NULL,                       -- scrapes.idx
  committed_at TEXT NOT NULL,
  path TEXT NOT NULL,                         -- file path in the raw repo at that commit
  blob TEXT NOT NULL,                         -- git blob (git cat-file -p <blob>)
  problem TEXT NOT NULL,                      -- 'conflict' | 'invalid' | 'empty'
  session TEXT,                               -- found by text search, when possible
  identifier TEXT                             -- found by text search, when possible
);
CREATE TABLE IF NOT EXISTS bills (            -- Table 2: one row per state and bill, its life story
  state TEXT NOT NULL,
  session TEXT NOT NULL,                      -- legislative_session
  identifier TEXT NOT NULL,                   -- bill identifier as scraped
  title TEXT,                                 -- title in its last-seen version
  first_idx INTEGER, first_at TEXT,           -- first scrape it appeared in
  last_idx INTEGER, last_at TEXT,             -- last scrape it appeared in
  scrapes_present INTEGER,                    -- scrapes it appeared in
  times_missing INTEGER,                      -- times it went missing and came back
  longest_missing_scrapes INTEGER,            -- longest such absence, in scrapes
  longest_missing_days REAL,                  -- and in days
  gone_for_good INTEGER,                      -- 1 if absent from every scrape after last_idx (there are later scrapes)
  session_continued INTEGER,                  -- 1 if other bills of its session appear after last_idx
  content_changes INTEGER,                    -- times its content changed (minus scraped_at/_id)
  actions_last INTEGER,                       -- actions in its last-seen version
  actions_gone_for_good INTEGER,              -- actions ever seen, not in the last version, not explained by a rewording
  votes_ever INTEGER,                         -- distinct votes ever seen for it
  votes_gone_for_good INTEGER,                -- of those, not in the last scrape it appeared in (re-keyed ones not counted)
  actions_chamber_swapped INTEGER,            -- its actions that came back under another chamber (counted once per scrape)
  votes_rekeyed INTEGER,                      -- its votes that came back under another key
  field_last_filled TEXT,                     -- JSON {field: last committed_at where it was filled}
  in_data_repo INTEGER,                       -- 1 if the data repo has its folder (sessions/<s>/bills/<id without spaces>), NULL: repo missing
  in_archive INTEGER,                         -- the same, govbot-archive <st>-legislation (July)
  in_archive_pre_rebuild INTEGER,             -- the same, govbot-archive -pre-rebuild-2026-07-21
  PRIMARY KEY (state, session, identifier)
);
CREATE TABLE IF NOT EXISTS sessions (         -- Table 3: one row per state and session, raw vs data repo vs archive
  state TEXT NOT NULL,
  session TEXT NOT NULL,
  raw_first_at TEXT,                          -- first scrape with a bill of this session (NULL: not in the raw history)
  raw_last_at TEXT,                           -- last scrape with a bill of this session
  raw_bills INTEGER,                          -- distinct bills of this session over the whole raw history
  raw_bills_last INTEGER,                     -- bills of this session in its last scrape
  data_repo_bills INTEGER,                    -- bill folders in <data-root>/<st>-legislation (NULL: repo missing)
  archive_bills INTEGER,                      -- in govbot-archive/<st>-legislation, frozen mid-July (NULL: clone missing/unfinished)
  archive_pre_rebuild_bills INTEGER,          -- in govbot-archive/<st>-legislation-pre-rebuild-2026-07-21 (NULL: same)
  PRIMARY KEY (state, session)
);
CREATE TABLE IF NOT EXISTS fields (           -- the field inventory (Q5), one row per state and field path
  state TEXT NOT NULL,
  field TEXT NOT NULL,                        -- as in scrape_fields.field
  kind TEXT,                                  -- 'top' | 'nested' | 'extras' | 'media' | 'other' (a dict field's keys)
  unusual INTEGER,                            -- 1 for a top-level key outside the usual OpenStates bill shape, or any extras key
  bills_latest INTEGER,                       -- bills with it in the latest scrape that has bills
  share_latest REAL,                          -- as a share of that scrape's bills
  best_share REAL,                            -- highest share in any scrape with bills
  best_at TEXT,                               -- the first scrape at that share
  first_at TEXT, last_at TEXT,                -- first and last scrape where any bill had it
  example TEXT,                               -- an example value (truncated), for unusual fields and extras
  PRIMARY KEY (state, field)
);
CREATE TABLE IF NOT EXISTS runs (             -- lineage: one row per state, the latest scan
  state TEXT PRIMARY KEY,
  scanner_commit TEXT,                        -- govbot commit of this scanner
  scanner_dirty INTEGER,                      -- 1 if the scanner folder had uncommitted changes
  raw_repo TEXT, raw_head TEXT,               -- raw scraper repo path and HEAD
  data_repo_head TEXT,                        -- data repo HEAD (NULL: missing)
  archive_head TEXT,                          -- govbot-archive <st>-legislation HEAD (NULL: missing)
  archive_pre_rebuild_head TEXT,              -- govbot-archive pre-rebuild HEAD (NULL: missing)
  started_at TEXT, seconds REAL,              -- when it ran and how long it took
  scrapes INTEGER,                            -- scrapes read
  cursor_sha TEXT, cursor_at TEXT             -- the last scrape read (for incremental runs later)
);
"""

TABLES = ("scrapes", "scrape_fields", "bad_files", "bills", "sessions", "fields", "runs")


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------


def git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True, text=True).stdout


class Blobs:
    """Read many git blobs through one `git cat-file --batch` process (as backfill_logs.py)."""

    def __init__(self, repo: Path) -> None:
        self.proc = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read_many(self, shas: list[str]):
        def feed() -> None:  # from a thread, so a long list can't fill both pipes and deadlock
            for sha in shas:
                self.proc.stdin.write(sha.encode() + b"\n")
            self.proc.stdin.flush()

        writer = threading.Thread(target=feed)
        writer.start()
        out = self.proc.stdout
        for sha in shas:
            header = out.readline().split()
            if len(header) != 3:
                raise RuntimeError(f"git cat-file: no blob {sha} ({header!r})")
            data = out.read(int(header[2]))
            out.read(1)
            yield sha, data
        writer.join()

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()
        self.proc.stdout.close()


def utc(when: str) -> str:
    """A git ISO time in UTC (self-hosted runs commit with -05:00), so text order is time order."""
    return datetime.fromisoformat(when).astimezone(timezone.utc).isoformat()


def scrape_commits(raw_repo: Path, state: str) -> list[tuple[str, str, str]]:
    """(sha, commit time, subject) of every commit touching _data/<state>/, oldest first. All
    parents, as backfill_logs.py: GA's 2026-07-21 auto-merge joined two real scrapes."""
    out = git(raw_repo, "log", "--reverse", "--date-order", "--format=%H%x09%cI%x09%s", "--", f"_data/{state}/")
    rows = []
    for line in out.splitlines():
        if line.strip():
            sha, when, subject = (line.split("\t", 2) + [""])[:3]
            rows.append((sha, utc(when), subject))
    return rows


def scrape_files(raw_repo: Path, sha: str, state: str) -> list[tuple[str, str]]:
    """(blob, path) of every file under _data/<state>/ at that commit."""
    out = git(raw_repo, "ls-tree", "-r", "-z", sha, f"_data/{state}/")
    files = []
    for entry in out.split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            _mode, kind, blob = meta.split()
            if kind == "blob":
                files.append((blob, path))
    return files


def repo_head(repo: Path) -> Optional[str]:
    """HEAD of a repo, or None when it is missing or still cloning (no HEAD commit yet)."""
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        return None
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD^{commit}"],
                       capture_output=True, text=True)
    return r.stdout.strip() or None


def repo_session_bills(repo: Path) -> Optional[dict[str, set[str]]]:
    """{session: bill folder names} at HEAD of a formatted data repo (country:us/state:<st>/sessions/
    <session>/bills/<id>/), found by walking trees, never a checkout. None when the repo is
    missing or unfinished."""
    if repo_head(repo) is None:
        return None
    # Find the 'sessions' tree within a few levels (state repos: country:us/state:<st>/sessions).
    frontier, sessions_dirs = [""], []
    for _depth in range(4):
        nxt = []
        for prefix in frontier:
            out = git(repo, "ls-tree", "-d", "-z", "HEAD", *( [prefix + "/"] if prefix else [] ), check=False)
            for entry in out.split("\0"):
                if not entry:
                    continue
                path = entry.split("\t", 1)[1]
                name = path.rsplit("/", 1)[-1]
                if name == ".git" or name.startswith("."):
                    continue
                (sessions_dirs if name == "sessions" else nxt).append(path)
        if sessions_dirs:
            break
        frontier = nxt
    folders: dict[str, set[str]] = {}
    for sdir in sessions_dirs:
        out = git(repo, "ls-tree", "-d", "-z", "--name-only", "HEAD", sdir + "/", check=False)
        for spath in filter(None, out.split("\0")):
            session = spath.rsplit("/", 1)[-1]
            bills = git(repo, "ls-tree", "-d", "-z", "--name-only", "HEAD", spath + "/bills/", check=False)
            folders.setdefault(session, set()).update(b.rsplit("/", 1)[-1] for b in bills.split("\0") if b)
    return folders


def folder_name(identifier: str) -> str:
    """A bill's folder in the data repo: its identifier without spaces (build_bill_path)."""
    return identifier.replace(" ", "")


# ---------------------------------------------------------------------------
# Reading one file
# ---------------------------------------------------------------------------


def filled(v: Any) -> bool:
    """A value that carries information: not None, not blank text, not an empty or all-blank list/dict."""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple)):
        return any(filled(x) for x in v)
    if isinstance(v, dict):
        return any(filled(x) for x in v.values())
    return True  # numbers and booleans


def ws_norm(v: Any) -> Any:
    """The value with every run of whitespace in its text collapsed to one space."""
    if isinstance(v, str):
        return " ".join(v.split())
    if isinstance(v, list):
        return [ws_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: ws_norm(x) for k, x in v.items()}
    return v


def h(v: Any) -> int:
    return int.from_bytes(hashlib.blake2b(json.dumps(v, sort_keys=True, ensure_ascii=False).encode(),
                                          digest_size=8).digest(), "big")


def media_bucket(media_type: str, url: str) -> str:
    m, u = (media_type or "").lower(), (url or "").lower().split("?")[0]
    if "html" in m or (not m and u.endswith((".htm", ".html"))):
        return "html"
    if "xml" in m and "officedocument" not in m or (not m and u.endswith(".xml")):
        return "xml"
    if "pdf" in m or (not m and u.endswith(".pdf")):
        return "pdf"
    if "word" in m or "msword" in m or "rtf" in m or (not m and u.endswith((".doc", ".docx", ".rtf"))):
        return "word"
    if not m and not u:
        return "none"
    return "other" if m else "unknown"


def classify(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    if name.startswith("bill_"):
        return "bill"
    if name.startswith("vote_event_"):
        return "vote"
    if name.startswith("event_"):
        return "event"
    return "other"


def bad_kind(raw: bytes) -> Optional[str]:
    if not raw.strip():
        return "empty"
    if CONFLICT_MARKER.search(raw):
        return "conflict"
    return None


def find_text(raw: bytes, key: str) -> Optional[str]:
    m = re.search(rb'"' + key.encode() + rb'"\s*:\s*"([^"]*)"', raw)
    return m.group(1).decode("utf-8", "replace") if m else None


class BillVersion:
    """What the scanner keeps about one version of a bill (one file's content)."""

    __slots__ = ("key", "bill_id", "content", "present", "top", "actions", "sponsors", "title", "extras_ex")

    def __init__(self, d: dict) -> None:
        self.bill_id = d.get("_id")  # votes point at it with `bill`
        self.key = (str(d.get("legislative_session") or ""), str(d.get("identifier") or ""))
        body = {k: v for k, v in d.items() if k not in VOLATILE}
        self.content = h(body)
        self.title = d.get("title") if isinstance(d.get("title"), str) else None
        present: set[str] = set()
        top: dict[str, tuple[int, int]] = {}
        extras_ex: dict[str, str] = {}
        for k, v in body.items():
            if k in IDENTITY or not filled(v):
                continue
            present.add(k)
            top[k] = (h(v), h(ws_norm(v)))
            if k == "jurisdiction":
                continue
            if isinstance(v, dict):
                for sub, sv in v.items():
                    if filled(sv):
                        p = f"{k}.{sub}"
                        present.add(p)
                        if k == "extras" and p not in extras_ex:
                            extras_ex[p] = json.dumps(sv, ensure_ascii=False)[:200]
            elif isinstance(v, list):
                for el in v:
                    if not isinstance(el, dict):
                        continue
                    for sub, sv in el.items():
                        if not filled(sv):
                            continue
                        present.add(f"{k}[].{sub}")
                        if isinstance(sv, list):
                            for el2 in sv:
                                if isinstance(el2, dict):
                                    for sub2, sv2 in el2.items():
                                        if filled(sv2):
                                            present.add(f"{k}[].{sub}[].{sub2}")
            if k not in STANDARD_BILL_KEYS and k not in extras_ex:
                extras_ex[k] = json.dumps(v, ensure_ascii=False)[:200]
        for k in ("versions", "documents"):
            for el in d.get(k) or []:
                if isinstance(el, dict):
                    for link in el.get("links") or [{"media_type": "", "url": el.get("url", "")}]:
                        if isinstance(link, dict):
                            present.add(f"{k}.media={media_bucket(link.get('media_type', ''), link.get('url', ''))}")
        self.present = frozenset(present)
        self.top = top
        acts = []
        for a in d.get("actions") or []:
            if isinstance(a, dict):
                org = a.get("organization_id") or a.get("organization") or a.get("chamber") or ""
                acts.append((str(a.get("date") or "")[:10], str(org), str(a.get("description") or "")))
        self.actions = tuple(acts)
        sp = []
        for s in d.get("sponsorships") or []:
            if isinstance(s, dict):
                sp.append((str(s.get("name") or ""), str(s.get("classification") or ""), bool(s.get("primary"))))
        self.sponsors = tuple(sp)
        self.extras_ex = extras_ex

    def richness(self) -> tuple:
        return (len(self.actions), len(self.present), self.content)


def norm_ident(ident: str) -> str:
    """A bill identifier without case, spaces or punctuation: "HJ RES 1", "HJRes 1" -> "HJRES1"."""
    return re.sub(r"[^0-9A-Z]", "", ident.upper())


def norm_index(keys) -> dict:
    """{(session, normalized identifier): bill key}, for identifiers that normalize to one bill only."""
    seen: dict[tuple, list] = defaultdict(list)
    for k in keys:
        seen[(k[0], norm_ident(k[1]))].append(k)
    return {n: ks[0] for n, ks in seen.items() if len(ks) == 1}


class VoteVersion:
    __slots__ = ("bill_key", "bill_ref", "vid", "content", "voters", "empty", "error", "page_text", "mismatch",
                 "error_name", "sigs")

    def __init__(self, d: dict) -> None:
        self.bill_key = (str(d.get("legislative_session") or ""), str(d.get("bill_identifier") or ""))
        self.bill_ref = d.get("bill")
        self.vid = (str(d.get("identifier") or ""), str(d.get("start_date") or ""),
                    str(d.get("motion_text") or ""), str(d.get("organization") or ""))
        self.content = h({k: v for k, v in d.items() if k not in VOTE_VOLATILE})
        votes = [v for v in d.get("votes") or [] if isinstance(v, dict)]
        # What identifies the same roll call when its key (roll-call id, date, motion, chamber)
        # changes: the same day and the same voters, or the same day and motion.
        day = str(d.get("start_date") or "")[:10]
        self.sigs = {("motion", day, " ".join(str(d.get("motion_text") or "").split()).lower())}
        if votes:
            self.sigs.add(("voters", day, h(sorted((str(v.get("voter_name")), str(v.get("option"))) for v in votes))))
        self.voters = len(votes)
        self.empty = not votes
        names = [str(v.get("voter_name") or "") for v in votes]
        err = [n for n in names if ERROR_VOTER.search(n.strip())]
        self.error = bool(err)
        self.error_name = err[0] if err else None
        self.page_text = any(len(n) > 60 or "\n" in n or len(n.split()) >= 8 for n in names)
        tally = Counter(str(v.get("option") or "") for v in votes)
        counts = {str(c.get("option") or ""): c.get("value") for c in d.get("counts") or [] if isinstance(c, dict)}
        # Yes, no and the total must match. Other options are named differently in the two
        # lists (KY counts "other", its voters say "not voting"), so they're only in the total.
        nums = {o: v for o, v in counts.items() if isinstance(v, int)}
        self.mismatch = bool(votes) and bool(nums) and (
            sum(nums.values()) != len(votes)
            or any(o in nums and nums[o] != tally.get(o, 0) for o in ("yes", "no")))


# ---------------------------------------------------------------------------
# The replay
# ---------------------------------------------------------------------------


class BillState:
    """Table 2 accumulators for one bill."""

    __slots__ = ("first", "last", "present", "missing", "longest_s", "longest_d", "changes", "field_last",
                 "version", "action_ever", "reworded_away", "votes_ever", "last_votes", "swapped",
                 "rekeyed", "rekeyed_away")

    def __init__(self, idx: int) -> None:
        self.first = self.last = idx
        self.present = 0
        self.missing = 0
        self.longest_s = 0
        self.longest_d = 0.0
        self.changes = 0
        self.field_last: dict[str, int] = {}
        self.version: Optional[BillVersion] = None
        self.action_ever: set[int] = set()
        self.reworded_away: set[int] = set()
        self.swapped = 0
        self.rekeyed = 0
        self.rekeyed_away: set[tuple] = set()
        self.votes_ever: set[tuple] = set()
        self.last_votes: set[tuple] = set()


def action_hashes(actions: Iterable[tuple]) -> set[int]:
    return {hash((d, o, " ".join(t.split()))) for d, o, t in actions}


def compare_actions(prev: tuple, now: tuple) -> tuple[int, int, int, int, int, list, list]:
    """(new, gone, reworded, ws_only, chamber_swapped, reworded pairs, swapped pairs) between two
    versions' actions, each pair (old, new). Gone/new pairs are matched in this order:
    1. differing only in whitespace (ws_only);
    2. same date and words, another chamber (chamber_swapped: TN's Senate bills read `lower`
       from 07-02, the same actions);
    3. same date + chamber, other words (reworded, as find_rewordings pairs MT's rewordings)."""
    gone = Counter(prev) - Counter(now)
    new = Counter(now) - Counter(prev)
    ws = 0
    by_norm = defaultdict(list)
    for (d, o, t), n in new.items():
        by_norm[(d, o, " ".join(t.split()))].append([(d, o, t), n])
    for (d, o, t), n in list(gone.items()):
        for slot in by_norm.get((d, o, " ".join(t.split())), []):
            m = min(n, slot[1])
            if m:
                ws += m
                n -= m
                slot[1] -= m
                new[slot[0]] -= m
                gone[(d, o, t)] -= m
    gone, new = +gone, +new
    swapped, swap_pairs = 0, []
    new_by_words = defaultdict(list)
    for a, n in new.items():
        new_by_words[(a[0], " ".join(a[2].split()))].extend([a] * n)
    for a, n in list(gone.items()):
        cands = [b for b in new_by_words.get((a[0], " ".join(a[2].split())), []) if b[1] != a[1]]
        while n and cands:
            b = cands.pop()
            new_by_words[(a[0], " ".join(a[2].split()))].remove(b)
            swapped += 1
            swap_pairs.append((a, b))
            n -= 1
            gone[a] -= 1
            new[b] -= 1
    gone, new = +gone, +new
    reworded, pairs = 0, []
    new_by_slot = defaultdict(list)
    for a, n in new.items():
        new_by_slot[(a[0], a[1])].extend([a] * n)
    for a, n in list(gone.items()):
        cands = new_by_slot.get((a[0], a[1]), [])
        while n and cands:
            b = cands.pop()
            reworded += 1
            pairs.append((a, b))
            n -= 1
            gone[a] -= 1
            new[b] -= 1
    gone, new = +gone, +new
    return sum(new.values()), sum(gone.values()), reworded, ws, swapped, pairs, swap_pairs


def parse_json(raw: bytes) -> Optional[Any]:
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None


def iso_hours(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 3600


def add_example(ex: dict, name: str, value: Any) -> None:
    lst = ex.setdefault(name, [])
    if len(lst) < EXAMPLES and value not in lst:
        lst.append(value)


def bill_label(key: tuple) -> str:
    return f"{key[0]} {key[1]}"


def scan_state(state: str, raw_repo: Path, log=print) -> dict[str, list]:
    """Replay the raw history of one state. Returns {table: rows} for every table but `runs`
    and `sessions` (which also need the data repos)."""
    commits = scrape_commits(raw_repo, state)
    blobs = Blobs(raw_repo)
    bills: dict[tuple, BillState] = {}
    prev_cache: dict[str, Any] = {}          # blob -> parsed version, previous scrape only
    prev_blobs: frozenset = frozenset()
    prev_content: frozenset = frozenset()
    prev_present: set[tuple] = set()
    prev_votes: dict[tuple, tuple] = {}     # (bill_key, vid) -> bill_key, previous scrape
    vote_last: dict[tuple, frozenset] = {}  # (bill_key, vid) -> content set, last seen
    vote_last_voters: dict[tuple, bool] = {}  # (bill_key, vid) -> last-seen version had voters
    vote_last_sigs: dict[tuple, set] = {}     # (bill_key, vid) -> its last-seen versions' sigs
    votes_seen: set[tuple] = set()
    gone_events: list[tuple[int, list]] = []                     # (idx, bill keys gone)
    loss_events: list[tuple[int, str, list]] = []                # (idx, field, bill keys)
    scrape_rows, field_rows, bad_rows = [], [], []
    field_first: dict[str, int] = {}
    field_extras_ex: dict[str, str] = {}
    times = [c[1] for c in commits]

    for idx, (sha, when, subject) in enumerate(commits):
        files = scrape_files(raw_repo, sha, state)
        kinds = Counter(classify(p) for _, p in files)
        # Every file is checked for damage; only bills and votes are parsed into versions.
        want = [b for b, p in files if b not in prev_cache]
        cache: dict[str, Any] = {}
        for b, p in files:
            if b in prev_cache:
                cache[b] = prev_cache[b]
        fetched = dict(blobs.read_many(sorted(set(want))))
        ex: dict[str, list] = {}
        bad = Counter()
        bad_keys: set[tuple] = set()
        now_versions: dict[tuple, list[BillVersion]] = defaultdict(list)
        vote_versions: list[VoteVersion] = []
        id_to_key: dict[str, tuple] = {}
        for b, p in files:
            kind = classify(p)
            if b not in cache:
                raw = fetched[b]
                problem = bad_kind(raw)
                d = None if problem else parse_json(raw)
                if problem is None and not isinstance(d, dict):
                    problem = "invalid"
                if problem:
                    sess = find_text(raw, "legislative_session")
                    ident = find_text(raw, "identifier" if kind == "bill" else "bill_identifier")
                    cache[b] = ("bad", problem, sess, ident)
                elif kind in ("bill", "vote"):
                    cache[b] = BillVersion(d) if kind == "bill" else VoteVersion(d)
                else:
                    cache[b] = "ok"  # a readable event, organization or jurisdiction file
            v = cache[b]
            if v == "ok":
                continue
            if isinstance(v, tuple):
                _, problem, sess, ident = v
                bad[problem] += 1
                bad_rows.append((state, idx, when, p, b, problem, sess, ident))
                if kind == "bill" and sess is not None and ident is not None:
                    bad_keys.add((sess, ident))
                add_example(ex, f"bad_{problem}", p.rsplit("/", 1)[-1])
            elif kind == "bill":
                now_versions[v.key].append(v)
                if v.bill_id:
                    id_to_key[v.bill_id] = v.key
            else:
                vote_versions.append(v)

        # Bills: pick one version per bill (the richest when duplicates differ).
        dup_conflicting = 0
        now: dict[tuple, BillVersion] = {}
        for key, vs in now_versions.items():
            if len({v.content for v in vs}) > 1:
                dup_conflicting += 1
                add_example(ex, "dup_bills_conflicting", bill_label(key))
            now[key] = max(vs, key=BillVersion.richness)
        bad_keys -= set(now)
        present = set(now)

        new_b = returned = changed = 0
        a_total = a_new = a_gone = a_rew = a_ws = a_swap = 0
        swap_pairs = Counter()
        renamed = 0
        rename_pairs = Counter()
        rew_pairs = Counter()
        fstat: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0, 0, 0, [], []])  # have had lost gained changed ws lostkeys changed-ex
        for key, v in now.items():
            a_total += len(v.actions)
            for f in v.present:
                fstat[f][0] += 1
            st = bills.get(key)
            if st is None:
                st = bills[key] = BillState(idx)
                new_b += 1
                a_new += len(v.actions)
            else:
                if key not in prev_present:
                    returned += 1
                    if st.last < idx - 1:
                        gap_s = idx - st.last - 1
                        gap_d = iso_hours(times[st.last], when) / 24
                        st.missing += 1
                        st.longest_s = max(st.longest_s, gap_s)
                        st.longest_d = max(st.longest_d, gap_d)
                old = st.version
                if old.content != v.content:
                    changed += 1
                    st.changes += 1
                    n_new, n_gone, n_rew, n_ws, n_swap, pairs, swaps = compare_actions(old.actions, v.actions)
                    a_new += n_new
                    a_gone += n_gone
                    a_rew += n_rew
                    a_ws += n_ws
                    a_swap += n_swap
                    st.swapped += n_swap
                    if n_gone:
                        add_example(ex, "actions_gone", bill_label(key))
                    if n_swap:
                        add_example(ex, "actions_chamber_swapped", bill_label(key))
                    for a, b in pairs + swaps:
                        st.reworded_away.add(hash((a[0], a[1], " ".join(a[2].split()))))
                    for a, b in pairs:
                        rew_pairs[(a[2], b[2])] += 1
                    for a, b in swaps:
                        swap_pairs[(a[1], b[1])] += 1
                    if (old.sponsors != v.sponsors and len(old.sponsors) == len(v.sponsors) and old.sponsors
                            and sorted(s[1:] for s in old.sponsors) == sorted(s[1:] for s in v.sponsors)):
                        renamed += 1
                        add_example(ex, "sponsors_renamed", bill_label(key))
                        olds = Counter(s[0] for s in old.sponsors) - Counter(s[0] for s in v.sponsors)
                        news = Counter(s[0] for s in v.sponsors) - Counter(s[0] for s in old.sponsors)
                        if len(olds) == 1 and len(news) == 1:
                            rename_pairs[(next(iter(olds)), next(iter(news)))] += 1
                for f in old.present | v.present:
                    was, isnow = f in old.present, f in v.present
                    s = fstat[f]
                    if was:
                        s[1] += 1
                        if not isnow:
                            s[2] += 1
                            s[6].append(key)
                    elif isnow:
                        s[3] += 1  # gained
                    if was and isnow and f in old.top and old.top[f][0] != v.top[f][0]:
                        s[4] += 1
                        if old.top[f][1] == v.top[f][1]:
                            s[5] += 1
                        if len(s[7]) < EXAMPLES:
                            s[7].append(bill_label(key))
            st.version = v
            st.last = idx
            st.present += 1
            st.action_ever |= action_hashes(v.actions)
            for f in v.present:
                st.field_last[f] = idx
                field_first.setdefault(f, idx)
            for f, e in v.extras_ex.items():
                field_extras_ex.setdefault(f, e)
            if len(ex.get("bills_new", [])) < EXAMPLES and st.first == idx:
                add_example(ex, "bills_new", bill_label(key))

        gone = sorted(k for k in prev_present if k not in present and k not in bad_keys)
        for k in gone[:EXAMPLES]:
            add_example(ex, "bills_gone", bill_label(k))
        if gone:
            gone_events.append((idx, gone))
        if rename_pairs:
            ex["sponsor_rename_top"] = [f"{a} -> {b} ({n})" for (a, b), n in rename_pairs.most_common(EXAMPLES)]
        if rew_pairs:
            ex["reworded_top"] = [f"{a} -> {b} ({n})" for (a, b), n in rew_pairs.most_common(EXAMPLES)]
        if swap_pairs:
            ex["chamber_swap_top"] = [f"{a} -> {b} ({n})" for (a, b), n in swap_pairs.most_common(EXAMPLES)]

        # Votes.
        vnow: dict[tuple, list[VoteVersion]] = defaultdict(list)
        orphan = 0
        by_norm = norm_index(present)
        for vv in vote_versions:
            bk = vv.bill_key
            if not bk[1] and vv.bill_ref in id_to_key:
                bk = id_to_key[vv.bill_ref]
            elif bk not in present:
                # The vote names its bill another way: USA "SJRes 5" / "HJ RES 1" for SJRES 5 / HJRES 1
                # (174 votes). The formatter files them under the bill; so does the scanner.
                bk = by_norm.get((bk[0], norm_ident(bk[1])), bk)
            vnow[(bk, vv.vid)].append(vv)
        counts = Counter()
        per_bill_votes: dict[tuple, set] = defaultdict(set)
        new_by_bill: dict[tuple, list] = defaultdict(list)
        for vk, vs in vnow.items():
            bk = vk[0]
            per_bill_votes[bk].add(vk)
            if bk not in present and bk not in bad_keys:
                orphan += 1
            cset = frozenset(v.content for v in vs)
            if vk not in votes_seen:
                counts["new"] += 1
                votes_seen.add(vk)
                new_by_bill[bk].append(vk)
            else:
                if vk not in prev_votes:
                    counts["returned"] += 1
                if vote_last.get(vk) != cset:
                    counts["changed"] += 1
                    add_example(ex, "votes_changed", bill_label(bk))
            had_voters = vote_last_voters.get(vk, False)
            # Empty only when every copy in this scrape is: AZ lists some roll calls twice, once
            # without voters (217 keys), which is not a vote losing its voters.
            if all(v.empty for v in vs):
                counts["empty"] += 1
                if had_voters:
                    counts["emptied"] += 1
                    add_example(ex, "votes_emptied", bill_label(bk))
            err = [v for v in vs if v.error]
            if err:
                counts["error"] += 1
                add_example(ex, "votes_error_voters", f"{bill_label(bk)}: {err[0].error_name!r}")
            if any(v.page_text for v in vs):
                counts["page"] += 1
                add_example(ex, "votes_page_text", bill_label(bk))
            if any(v.mismatch for v in vs):
                counts["mismatch"] += 1
                add_example(ex, "votes_count_mismatch", bill_label(bk))
            vote_last[vk] = cset
            vote_last_voters[vk] = any(not v.empty for v in vs)
            vote_last_sigs[vk] = set().union(*(v.sigs for v in vs))
        v_gone = v_rekeyed = 0
        key_fields = Counter()
        for vk in sorted(prev_votes):
            if vk not in vnow and vk[0] in present:
                v_gone += 1
                # Back under another key? Match it to a vote new tonight on the same bill.
                cands = new_by_bill.get(vk[0], [])
                hit = next((n for n in cands if vote_last_sigs.get(vk, set()) & vote_last_sigs[n]), None)
                if hit is None:
                    add_example(ex, "votes_gone", bill_label(vk[0]))
                    continue
                cands.remove(hit)
                v_rekeyed += 1
                bills[vk[0]].rekeyed += 1
                bills[vk[0]].rekeyed_away.add(vk)
                add_example(ex, "votes_rekeyed", bill_label(vk[0]))
                for name, a, b in zip(("roll-call id", "date", "motion", "chamber"), vk[1], hit[1]):
                    if a != b:
                        key_fields[name] += 1
        if key_fields:
            ex["rekeyed_fields"] = [f"{k} ({n})" for k, n in key_fields.most_common()]
        for key in present:
            st = bills[key]
            vs = per_bill_votes.get(key, set())
            st.votes_ever |= vs
            st.last_votes = vs

        # Field rows.
        for f, s in fstat.items():
            if s[0] or s[2]:
                field_rows.append([state, idx, when, f, s[0], s[1], s[2], None, s[3], s[4], s[5],
                                   json.dumps({"lost": [bill_label(k) for k in s[6][:EXAMPLES]],
                                               "changed": s[7]}, ensure_ascii=False)])
                if s[2]:
                    loss_events.append((len(field_rows) - 1, f, s[6]))

        blob_set = frozenset(b for b, _ in files)
        content_set = frozenset([v.content for v in now.values()] + [c for vk in vnow for c in vote_last[vk]])
        by_session = Counter(k[0] for k in present)
        scrape_rows.append([
            state, idx, sha, when, subject,
            None if idx == 0 else round(iso_hours(times[idx - 1], when), 2),
            len(files), kinds["bill"], kinds["vote"], kinds["event"], kinds["other"],
            len(present), json.dumps(dict(sorted(by_session.items())), ensure_ascii=False),
            round(sum(len(vs) for vs in now_versions.values()) / len(present), 3) if present else None,
            dup_conflicting,
            bad["conflict"], bad["invalid"], bad["empty"], len(bad_keys),
            int(idx > 0 and blob_set == prev_blobs), int(idx > 0 and content_set == prev_content),
            new_b, returned, len(gone), None, changed,
            a_total, a_new, a_gone, a_rew, a_ws, a_swap,
            len(vnow), counts["new"], counts["returned"], counts["changed"], v_gone, v_rekeyed,
            counts["empty"], counts["emptied"], counts["error"], counts["page"], counts["mismatch"], orphan,
            renamed, json.dumps(ex, ensure_ascii=False),
        ])
        prev_cache = cache
        prev_blobs, prev_content = blob_set, content_set
        prev_present = present | bad_keys  # an unreadable bill is not "gone"; compare it again next time
        prev_votes = {vk: vk[0] for vk in vnow}
        if (idx + 1) % 25 == 0 or idx + 1 == len(commits):
            log(f"  {state}: {idx + 1}/{len(commits)} scrapes ({when[:10]}), {len(bills)} bills so far")
    blobs.close()

    # Late columns: did gone bills and lost fields come back?
    for idx, keys in gone_events:
        scrape_rows[idx][24] = sum(1 for k in keys if bills[k].last > idx)
    for row_i, f, keys in loss_events:
        idx = field_rows[row_i][1]
        field_rows[row_i][7] = sum(1 for k in keys if bills[k].field_last.get(f, -1) > idx)

    last_idx = len(commits) - 1
    session_last: dict[str, int] = {}
    for (sess, _), st in bills.items():
        session_last[sess] = max(session_last.get(sess, -1), st.last)
    bill_rows = []
    for (sess, ident), st in sorted(bills.items()):
        v = st.version
        last_keys = action_hashes(v.actions)
        bill_rows.append((
            state, sess, ident, v.title, st.first, times[st.first], st.last, times[st.last], st.present,
            st.missing, st.longest_s, round(st.longest_d, 2), int(st.last < last_idx),
            int(session_last[sess] > st.last), st.changes, len(v.actions),
            len(st.action_ever - last_keys - st.reworded_away), len(st.votes_ever),
            len(st.votes_ever - st.last_votes - st.rekeyed_away), st.swapped, st.rekeyed,
            json.dumps({f: times[i] for f, i in sorted(st.field_last.items())}, ensure_ascii=False),
        ))

    # Field inventory.
    per_scrape = defaultdict(dict)
    for r in field_rows:
        per_scrape[r[1]][r[3]] = r[4]
    with_bills = [r for r in scrape_rows if r[11]]
    latest = with_bills[-1] if with_bills else None
    inv_rows = []
    for f in sorted(field_first):
        best, best_at = 0.0, None
        last_seen = None
        for r in with_bills:
            n = per_scrape[r[1]].get(f, 0)
            if n:
                last_seen = r[3]
            share = n / r[11]
            if share > best + 1e-12:
                best, best_at = share, r[3]
        n_latest = per_scrape[latest[1]].get(f, 0) if latest else 0
        top = f.split(".", 1)[0].split("[", 1)[0]
        if "media=" in f:
            kind = "media"
        elif f.startswith("extras."):
            kind = "extras"
        elif "[]" in f:
            kind = "nested"
        elif "." in f:
            kind = "other"
        else:
            kind = "top"
        unusual = int(kind == "extras" or (kind == "top" and top not in STANDARD_BILL_KEYS))
        inv_rows.append((state, f, kind, unusual, n_latest, round(n_latest / latest[11], 4) if latest else None,
                         round(best, 4), best_at, times[field_first[f]], last_seen,
                         field_extras_ex.get(f) if unusual else None))

    return {"scrapes": scrape_rows, "scrape_fields": field_rows, "bad_files": bad_rows,
            "bills": bill_rows, "fields": inv_rows,
            "_session_stats": _session_stats(bills, times), "_commits": commits}


def _session_stats(bills: dict, times: list) -> dict[str, list]:
    stats: dict[str, list] = {}
    last_by_session: dict[str, int] = {}
    for (sess, _), st in bills.items():
        last_by_session[sess] = max(last_by_session.get(sess, -1), st.last)
    for (sess, _), st in bills.items():
        s = stats.setdefault(sess, [None, None, 0, 0])
        s[0] = min(s[0], st.first) if s[0] is not None else st.first
        s[1] = max(s[1], st.last) if s[1] is not None else st.last
        s[2] += 1
        s[3] += int(st.last == last_by_session[sess])
    return {sess: [times[a], times[b], n, n_last] for sess, (a, b, n, n_last) in stats.items()}


def session_rows(state: str, stats: dict, data: Optional[dict], archive: Optional[dict],
                 pre: Optional[dict]) -> list[tuple]:
    names = set(stats) | set(data or {}) | set(archive or {}) | set(pre or {})
    rows = []
    for s in sorted(names):
        raw = stats.get(s, [None, None, 0, 0])
        rows.append((state, s, raw[0], raw[1], raw[2], raw[3],
                     None if data is None else data.get(s, 0),
                     None if archive is None else archive.get(s, 0),
                     None if pre is None else pre.get(s, 0)))
    return rows


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db), timeout=600)
    con.executescript(SCHEMA)
    # CREATE TABLE IF NOT EXISTS never changes an existing table, so a database made by an older
    # scanner keeps its old columns. Stop rather than write rows that don't fit.
    want = sqlite3.connect(":memory:")
    want.executescript(SCHEMA)
    for t in TABLES:
        cols = lambda c: [r[1] for r in c.execute(f"PRAGMA table_info({t})")]
        if cols(con) != cols(want):
            con.close()
            raise SystemExit(f"{db}: table {t} has an older schema than scan.py. The database is derived "
                             f"data: delete it (or pass a new --db) and re-scan.")
    return con


def write_state(con: sqlite3.Connection, state: str, tables: dict[str, list], run: tuple) -> None:
    with con:  # one transaction: a re-scan replaces the state's rows
        for t in TABLES:
            con.execute(f"DELETE FROM {t} WHERE state = ?", (state,))
        for t in ("scrapes", "scrape_fields", "bad_files", "bills", "sessions", "fields"):
            rows = tables.get(t) or []
            if rows:
                marks = ",".join("?" * len(rows[0]))
                con.executemany(f"INSERT INTO {t} VALUES ({marks})", rows)
        con.execute(f"INSERT INTO runs VALUES ({','.join('?' * len(run))})", run)


def scanner_lineage() -> tuple[Optional[str], int]:
    here = Path(__file__).resolve().parent
    commit = git(here, "rev-parse", "HEAD", check=False).strip() or None
    dirty = int(bool(git(here, "status", "--porcelain", "--", ".", check=False).strip()))
    return commit, dirty


def run_state(state: str, raw_root: Path, data_root: Path, archive_root: Path, db: Path,
              out_dir: Optional[Path]) -> str:
    started = time.time()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw_repo = raw_root / f"{state}-legislation"
    if repo_head(raw_repo) is None:
        return f"{state}: no raw repo at {raw_repo}, skipped"
    tables = scan_state(state, raw_repo, log=lambda m: print(m, file=sys.stderr, flush=True))
    data_repo = data_root / f"{state}-legislation"
    arch = archive_root / f"{state}-legislation"
    pre = archive_root / f"{state}-legislation{PRE_REBUILD_SUFFIX}"
    repos = [repo_session_bills(r) for r in (data_repo, arch, pre)]
    tables["sessions"] = session_rows(state, tables["_session_stats"],
                                      *[None if f is None else {s: len(b) for s, b in f.items()} for f in repos])
    has = lambda f, sess, ident: None if f is None else int(folder_name(ident) in f.get(sess, ()))
    tables["bills"] = [row + tuple(has(f, row[1], row[2]) for f in repos) for row in tables["bills"]]
    commits = tables["_commits"]
    commit, dirty = scanner_lineage()
    run = (state, commit, dirty, str(raw_repo), repo_head(raw_repo), repo_head(data_repo), repo_head(arch),
           repo_head(pre), started_at, round(time.time() - started, 1), len(commits),
           commits[-1][0] if commits else None, commits[-1][1] if commits else None)
    con = connect(db)
    write_state(con, state, tables, run)
    if out_dir is not None:
        import report  # same folder
        report.write_report(con, state, out_dir / state / "report.md")
    con.close()
    missing = [n for n, hd in (("data repo", run[5]), ("archive", run[6]), ("pre-rebuild archive", run[7])) if hd is None]
    note = f" (not found or unfinished: {', '.join(missing)})" if missing else ""
    return f"{state}: {len(commits)} scrapes, {len(tables['bills'])} bills, {run[9]} s{note}"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("states", nargs="+", help="jurisdiction codes, e.g. wy ky ar")
    p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    p.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="folder for history.sqlite and <st>/report.md")
    p.add_argument("--db", type=Path, help="database (default <out>/history.sqlite)")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--jobs", type=int, default=1, help="states scanned at once")
    a = p.parse_args(argv)
    db = a.db or a.out / "history.sqlite"
    connect(db).close()  # create the schema once, before any worker
    args = [(s.lower(), a.raw_root, a.data_root, a.archive_root, db, None if a.no_report else a.out)
            for s in a.states]
    if a.jobs > 1:
        from multiprocessing import Pool
        with Pool(a.jobs) as pool:
            for msg in pool.starmap(run_state, args):
                print(msg, flush=True)
    else:
        for x in args:
            print(run_state(*x), flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
