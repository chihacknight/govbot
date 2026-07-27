#!/usr/bin/env python3
"""Incremental filter for the `govbot logs | govbot tag` dashboard pipeline.

`govbot tag` runs one embedding forward pass per bill it receives on stdin, so
tagging every bill on every daily dashboard build is slow (~1-2h at ~140k bills).
This filter sits between `govbot logs` and `govbot tag` and passes through only
bills that are **new or whose tag-relevant text changed** since the last run,
based on a small per-repo ledger. After the first full pass, each run only
re-tags what actually changed, keeping the nightly build to minutes.

Why a ledger is needed rather than relying on cached tag files: `govbot tag`
records a bill only when it matches at least one tag (see run_tag_command in
actions/govbot/src/main.rs), so bills that match no topic leave no trace and
would be re-embedded every run. The ledger records **every** bill it sees
(matched or not), so unchanged bills are skipped regardless of whether they tag.

Pipeline usage (see .github/workflows/deploy-docs.yml):

    govbot logs --repos <loc> --govbot-dir <D> --join bill --limit none --filter none \
      | python3 scripts/filter_new_bills.py --ledger <cache>/<repo>/ledger.json \
      | ( cd <repo> && govbot tag --govbot-dir <model-dir> --overwrite )

Notes:
* Use `--join bill` (not the default `bill,tags`): the `tags` join would inject a
  bill's own tags into the line after the first run, churning the content hash.
* Pair with `govbot tag --overwrite` so a **changed** bill actually re-tags — the
  tagger's own fast path skips a bill by id presence alone and would otherwise
  keep stale tags for amended bills.
* The ledger is per-repo so parallel workers never touch the same file.

Only the Python standard library is used.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


def content_hash(entry):
    """Stable hash of the tag-relevant content of one `govbot logs` line.

    Hashes the bill metadata plus this line's action — a superset of the text
    `govbot tag` embeds (see ocd_files_select_default in
    actions/govbot/src/selectors.rs). Deliberately excludes volatile top-level
    fields (`id`, `sources`, `timestamp`) so an unchanged bill hashes the same
    across runs. Falls back to the whole entry (minus those fields) if the line
    is not shaped as expected.
    """
    bill = entry.get("bill")
    if bill is not None:
        material = {"bill": bill, "action": (entry.get("log") or {}).get("action")}
    else:
        material = {k: v for k, v in entry.items()
                    if k not in ("id", "sources", "timestamp")}
    blob = json.dumps(material, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_ledger(path):
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as err:
        print(f"filter_new_bills: ignoring unreadable ledger {path}: {err}",
              file=sys.stderr)
        return {}


def save_ledger(path, ledger):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(ledger, sort_keys=True, separators=(",", ":")))
    os.replace(tmp, path)  # atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", required=True,
                        help="Path to this repo's ledger JSON (bill_id -> content hash)")
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    previous = load_ledger(ledger_path)
    current = {}  # every bill seen this run -> its current hash (the next ledger)

    read = emitted = 0
    for line in sys.stdin:
        stripped = line.strip()
        if not stripped:
            continue
        read += 1
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            # Not JSON we understand; pass it through untouched rather than drop.
            sys.stdout.write(line)
            emitted += 1
            continue

        bill_id = entry.get("id")
        if not isinstance(bill_id, str):
            # No stable id to dedup on; let the tagger handle it.
            sys.stdout.write(line)
            emitted += 1
            continue

        if bill_id in current:
            # Another log line for a bill already decided this run (govbot logs
            # emits one line per action). The first, most-recent line wins.
            continue

        h = content_hash(entry)
        current[bill_id] = h
        if previous.get(bill_id) != h:  # new bill or changed content
            sys.stdout.write(line)
            emitted += 1

    save_ledger(ledger_path, current)
    print(f"filter_new_bills: {len(current)} bills, {emitted} new/changed "
          f"emitted, {len(current) - emitted} unchanged skipped "
          f"(read {read} lines)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
