#!/usr/bin/env python3
"""
Replay a raw scraper repo's history into a formatted repo's per-bill logs.

    python3 backfill_logs.py <formatted-repo> <raw-scraper-repo> --report-dir <dir> [--dry-run]

Every night's scrape (a commit to _data/<state>/ in the raw scraper repo) is the
whole dataset. This replays those commits oldest to newest and, for each one,
appends the actions and votes not yet in each bill's action_logs.jsonl /
vote_event_logs.jsonl, stamped with first_seen = that scrape's commit time. That
is what the nightly formatter would have written had the .jsonl layout existed
all along, using the same rules (utils/log_jsonl.py): one batch per raw file in
the government's date order, the same duplicate checks, vote corrections under
the same id. It recovers votes the old layout lost and gives every entry the
night it first appeared.

Differences from the nightly formatter, on purpose:
- It touches only the two .jsonl files. No metadata.json, no placeholders.
- It writes only into bill folders that already exist. A bill in the raw history
  with no folder is listed in the report, never created (that would need a
  metadata.json too).
- It skips the formatter's "same action count as metadata.json, skip the bill"
  shortcut and compares every action with the log itself, so actions lost by
  that shortcut are recovered.

Part of the conversion plan (tamara-notes/processes/workstreams/jsonl-logs.md):
run this on the full-history formatted repo first, then convert_logs.py, which
folds in the old logs/*.json files the raw history doesn't cover.

Re-runs: the last scrape replayed is recorded in
<report-dir>/log_backfill-<state>.json (not in the repo). A second run resumes
after it, so it never replays a scrape twice (replaying a corrected vote's
history again would append its corrections again). Without that file the repo
must have no .jsonl logs yet. Nothing is written until the whole replay
succeeds.

Git is read with `git cat-file --batch`. Raw filenames are per-scrape UUIDs, so
every file of every scrape is looked at; a file whose exact content (blob) was
already replayed is skipped when that can't change the result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from utils import log_jsonl as L
from utils.path_utils import build_bill_path


class Blobs:
    """Read many git blobs through one `git cat-file --batch` process."""

    def __init__(self, repo: Path) -> None:
        self.proc = subprocess.Popen(
            ["git", "-C", str(repo), "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )

    def read_many(self, shas: list[str]):
        """Yield (sha, bytes) for each sha, in order. Requests are written from a
        thread so a long list can't fill both pipes and deadlock."""

        def feed() -> None:
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
            size = int(header[2])
            data = out.read(size)
            out.read(1)  # the newline after each blob
            yield sha, data
        writer.join()

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def scrape_commits(raw_repo: Path, state: str) -> list[tuple[str, str]]:
    """(sha, commit time) of every commit that touched _data/<state>/, oldest
    first. All parents, not just the first: GA's 2026-07-21 auto-merge joined two
    real scrapes. The commit time (%cI) is what the nightly pipeline stamps as
    first_seen (actions/format/action.yml)."""
    out = git(raw_repo, "log", "--reverse", "--date-order", "--format=%H %cI", "--", f"_data/{state}/")
    return [tuple(line.split(" ", 1)) for line in out.splitlines() if line.strip()]


def scrape_files(raw_repo: Path, sha: str, state: str) -> list[tuple[str, str]]:
    """(blob, filename) of the bill and vote files in one scrape, by filename."""
    out = git(raw_repo, "ls-tree", "-z", sha, f"_data/{state}/")
    files = []
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        _mode, kind, blob = meta.split()
        name = path.rsplit("/", 1)[-1]
        if kind == "blob" and name.endswith(".json") and name.startswith(("bill_", "vote_event_")):
            files.append((blob, name))
    return sorted(files, key=lambda f: f[1])


class BillLog:
    """One bill's two logs, in memory: the lines already on disk plus the new ones."""

    def __init__(self, bill_dir: Path) -> None:
        self.dir = bill_dir
        actions = L.read_lines(bill_dir / L.ACTION_LOG_FILE)
        self.action_seen = {L.action_key(line.get("action") or {}) for line in actions}
        self.action_ids = {line.get("id") for line in actions}
        self.action_id_of = {L.action_key(line.get("action") or {}): line.get("id") for line in actions}
        # The bill's actions in the last scrape that had it, and that file's blob:
        # find_rewordings() compares tonight's actions with these, as the nightly
        # writer compares with metadata.json.
        self.prev_actions: Optional[list[dict[str, Any]]] = None
        self.prev_blob: Optional[bytes] = None
        self.votes = L.read_lines(bill_dir / L.VOTE_EVENT_LOG_FILE)
        self.vote_ids = {line.get("id") for line in self.votes}
        self.votes_on_disk = len(self.votes)
        self.new_actions: list[dict[str, Any]] = []
        # Bumped whenever a vote line is added, so a vote file seen before can be
        # skipped only if nothing in this bill's vote log changed since.
        self.vote_version = 0

    def write(self) -> None:
        L._append(self.dir / L.ACTION_LOG_FILE, self.new_actions, "action", keep_order=True)
        L._append(self.dir / L.VOTE_EVENT_LOG_FILE, self.votes[self.votes_on_disk:], "vote_event", keep_order=True)


class Replay:
    def __init__(self, repo: Path, state: str) -> None:
        self.repo = repo
        self.state = state
        self.bills: dict[Path, Optional[BillLog]] = {}
        self.missing: dict[str, int] = {}  # "session/bill" -> raw files naming it
        # bill blob -> its bill folder (None: a bill with no folder, never re-read)
        self.bill_blobs_done: dict[bytes, Optional[Path]] = {}
        self.vote_blobs_done: dict[bytes, tuple[Path, int]] = {}
        self.unreadable: dict[str, int] = {}  # scrape date -> files that aren't valid JSON
        self.unreadable_examples: list[dict[str, Any]] = []
        self.stats = {
            "scrapes_replayed": 0,
            "files_seen": 0,
            "files_parsed": 0,
            "actions_added": 0,
            "votes_added": 0,
            "vote_corrections": 0,
            "action_corrections": 0,
            "action_rewordings_unpaired": 0,
            "files_unreadable": 0,
            "files_without_bill_or_session": 0,
        }

    def bill_log(self, session: str, identifier: str) -> Optional[BillLog]:
        bill_dir = build_bill_path(self.repo, self.state, session, identifier)
        if bill_dir not in self.bills:
            self.bills[bill_dir] = BillLog(bill_dir) if bill_dir.is_dir() else None
        log = self.bills[bill_dir]
        if log is None:
            key = f"{session}/{bill_dir.name}"
            self.missing[key] = self.missing.get(key, 0) + 1
        return log

    def wants(self, blob: str, name: str) -> bool:
        """Whether a raw file could add anything. A bill blob replayed before adds
        no action, and is skipped when it is also its bill's latest version (so the
        "previous scrape" find_rewordings() needs stays right). A vote blob
        replayed before adds nothing as long as its bill's vote log hasn't changed
        since (otherwise it might now be a correction back to an earlier version)."""
        key = bytes.fromhex(blob)
        if name.startswith("bill_"):
            if key not in self.bill_blobs_done:
                return True
            bill_dir = self.bill_blobs_done[key]
            log = self.bills.get(bill_dir) if bill_dir is not None else None
            return log is not None and log.prev_blob != key
        done = self.vote_blobs_done.get(key)
        if done is None:
            return True
        bill_dir, version = done
        log = self.bills.get(bill_dir)
        return log is None or log.vote_version != version

    def apply(self, blob: str, name: str, raw: bytes, first_seen: str) -> None:
        self.stats["files_parsed"] += 1
        try:
            data = json.loads(raw)
        except ValueError as e:
            # The nightly formatter files these under .windycivi/errors/invalid_json.
            self.stats["files_unreadable"] += 1
            self.unreadable[first_seen[:10]] = self.unreadable.get(first_seen[:10], 0) + 1
            if len(self.unreadable_examples) < 10:
                self.unreadable_examples.append({"scrape": first_seen, "file": name, "bytes": len(raw), "error": str(e)})
            return
        if name.startswith("bill_"):
            log = self.apply_bill(data, first_seen)
            self.bill_blobs_done[bytes.fromhex(blob)] = log.dir if log is not None else None
            if log is not None:
                log.prev_blob = bytes.fromhex(blob)
        else:
            log = self.apply_vote(data, first_seen)
            if log is not None:
                self.vote_blobs_done[bytes.fromhex(blob)] = (log.dir, log.vote_version)

    def apply_bill(self, data: dict[str, Any], first_seen: str) -> Optional[BillLog]:
        # Same fields handlers/bill.py uses.
        identifier, session = data.get("identifier"), data.get("legislative_session")
        if not identifier or not session:
            self.stats["files_without_bill_or_session"] += 1
            return None
        log = self.bill_log(session, identifier)
        if log is None:
            return None
        sources = data.get("sources", [])
        actions = data.get("actions", [])
        rewordings = L.find_rewordings(log.prev_actions, actions)
        lines = [L.action_line(a, identifier, sources, session, first_seen) for a in actions]
        ids_before = len(log.action_ids)
        added = L.select_new_actions(log.action_seen, log.action_ids, lines, rewordings, log.action_id_of)
        log.new_actions.extend(L.order_batch(added, "action"))
        log.prev_actions = actions
        self.stats["actions_added"] += len(added)
        # A new action adds an id; a rewording reuses one.
        self.stats["action_corrections"] += len(added) - (len(log.action_ids) - ids_before)
        self.stats["action_rewordings_unpaired"] += rewordings.unpaired
        return log

    def apply_vote(self, data: dict[str, Any], first_seen: str) -> Optional[BillLog]:
        # Same fields handlers/vote_event.py uses.
        identifier, session = data.get("bill_identifier"), data.get("legislative_session")
        if not identifier or not session:
            self.stats["files_without_bill_or_session"] += 1
            return None
        log = self.bill_log(session, identifier)
        if log is None:
            return None
        ids_before = len(log.vote_ids)
        added = L.select_new_votes(log.votes, log.vote_ids, [L.vote_event_line(data, first_seen)])
        if added:
            log.votes.extend(added)
            log.vote_version += 1
            self.stats["votes_added"] += len(added)
            # A new vote adds an id; a correction reuses one.
            self.stats["vote_corrections"] += len(added) - (len(log.vote_ids) - ids_before)
        return log

    def write(self) -> int:
        touched = 0
        for log in self.bills.values():
            if log is not None and (log.new_actions or len(log.votes) > log.votes_on_disk):
                log.write()
                touched += 1
        return touched


def repo_state(repo: Path) -> str:
    states = [p.name.split(":", 1)[1] for p in (repo / "country:us").glob("state:*") if p.is_dir()]
    if len(states) != 1:
        raise SystemExit(f"error: expected one country:us/state:* folder in {repo}, found {states}")
    return states[0]


def has_jsonl_logs(repo: Path) -> bool:
    return any(repo.glob(f"country:us/state:*/sessions/*/bills/*/{L.ACTION_LOG_FILE}")) or any(
        repo.glob(f"country:us/state:*/sessions/*/bills/*/{L.VOTE_EVENT_LOG_FILE}")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo", type=Path, help="Formatted repo root (the folder holding country:us/)")
    parser.add_argument("raw_repo", type=Path, help="Raw scraper repo, full history (the folder holding _data/)")
    parser.add_argument("--report-dir", type=Path, required=True, help="Where the run's report and re-run cursor go (not in the repo)")
    parser.add_argument("--dry-run", action="store_true", help="Replay and report, write nothing")
    args = parser.parse_args()

    repo, raw_repo = args.repo.resolve(), args.raw_repo.resolve()
    state = repo_state(repo)
    report_path = args.report_dir / f"log_backfill-{state}.json"

    commits = scrape_commits(raw_repo, state)
    if not commits:
        print(f"error: no commits touch _data/{state}/ in {raw_repo}", file=sys.stderr)
        return 2

    previous = json.loads(report_path.read_text()) if report_path.exists() else None
    if previous:
        shas = [sha for sha, _ in commits]
        if previous.get("last_scrape") not in shas:
            print(f"error: {report_path} names scrape {previous.get('last_scrape')}, not in {raw_repo}", file=sys.stderr)
            return 2
        commits = commits[shas.index(previous["last_scrape"]) + 1 :]
    elif has_jsonl_logs(repo):
        print(
            f"error: {repo} already has .jsonl logs and there is no {report_path}. The backfill runs "
            "first, before convert_logs.py and the formatter; it can't tell which scrapes those covered.",
            file=sys.stderr,
        )
        return 2

    # Lineage: which version of the rules (utils/log_jsonl.py) wrote these lines.
    here = Path(__file__).resolve().parent
    code = {
        "govbot_commit": git(here, "rev-parse", "HEAD").strip(),
        "uncommitted_changes": bool(git(here, "status", "--porcelain", "--", ".").strip()),
    }

    replay = Replay(repo, state)
    blobs = Blobs(raw_repo)
    started = time.time()
    try:
        for n, (sha, committed_at) in enumerate(commits, start=1):
            files = scrape_files(raw_repo, sha, state)
            replay.stats["files_seen"] += len(files)
            # Read what's needed in one batch, then apply in filename order. A file
            # skipped by the batch is checked again when its turn comes, since an
            # earlier file in this scrape may have changed its bill's vote log.
            fetched = dict(blobs.read_many(sorted({blob for blob, name in files if replay.wants(blob, name)})))
            for blob, name in files:
                if blob in fetched:
                    replay.apply(blob, name, fetched[blob], committed_at)
                elif replay.wants(blob, name):
                    [(_, raw)] = blobs.read_many([blob])
                    replay.apply(blob, name, raw, committed_at)
            replay.stats["scrapes_replayed"] += 1
            if n % 10 == 0 or n == len(commits):
                print(
                    f"  {n}/{len(commits)} scrapes ({committed_at[:10]}), {replay.stats['actions_added']} actions, "
                    f"{replay.stats['votes_added']} votes, {time.time() - started:.0f}s",
                    file=sys.stderr,
                )
    finally:
        blobs.close()

    bills_touched = 0 if args.dry_run else replay.write()
    missing = sorted(replay.missing.items(), key=lambda kv: (-kv[1], kv[0]))
    report = {
        "state": state,
        "repo": str(repo),
        "raw_repo": str(raw_repo),
        "first_scrape": commits[0][0] if commits else None,
        "last_scrape": commits[-1][0] if commits else (previous or {}).get("last_scrape"),
        "last_scrape_at": commits[-1][1] if commits else (previous or {}).get("last_scrape_at"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        **code,
        **replay.stats,
        "bills_touched": bills_touched,
        "bills_missing": len(missing),
        "files_unreadable_by_scrape": replay.unreadable,
        "files_unreadable_examples": replay.unreadable_examples,
        "bills_missing_list": [{"bill": k, "raw_files": v} for k, v in missing],
    }
    summary = {k: v for k, v in report.items() if k not in ("bills_missing_list", "files_unreadable_examples")}
    summary["bills_missing_examples"] = [k for k, _ in missing[:10]]
    print(json.dumps(summary, indent=2))
    if not args.dry_run:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"report: {report_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
