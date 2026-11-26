"""
Guards for the nightly bill update.

Every bill in a scrape is processed every night, and its metadata.json is
rewritten from tonight's scrape. Scrapers sometimes fail on part of a page and
return a bill with a field empty that was filled the night before. Two guards:

(a) keep_nonempty: never replace a non-empty field with an empty one. Last
    night's value stays until the field comes back, and every night it's kept is
    listed in .windycivi/errors/kept_empty_fields.json (bill, field, the scrape it
    was first kept on). Only the first night is recorded, so the file changes only
    when a field is first kept or comes back, not every night it stays missing;
    the printed "Kept last night's ..." line shows it's ongoing.
(c) finish: a field that vanished from most of a state's bills in one night is
    a scraper regression, not news. It prints a GitHub ::warning:: and writes
    .windycivi/errors/field_regressions.json (a JSON list, one entry per field:
    state, night, field, bills_lost, bills_had) for the daily audit in
    actions/openstates-scrape-audits/ to read. The file is removed on a night
    nothing fires. The run goes on: guard (a) has already kept the data.

Guard (b), whitespace-only description changes, is in merge_actions
(processing_tracker.py), which matches actions the way the action log does.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

# The fields guard (a) protects. Scrapers lose a field on every bill at once and
# often never get it back: IL's scrape has had no abstracts since 2026-07-13
# (8,648 bills) and KY's no sponsors since 2026-08-20 (1,707 bills); NH lost
# sponsors on 1,143 bills on 2025-12-25 and 12-30, and versions on 1,126 on
# 2026-08-21, then recovered (measured on the raw history, see
# tamara-notes/processes/workstreams/shared-docs/bill-skip-option-c.md). Without
# the guard every IL abstract and KY sponsor would leave metadata.json the first
# night, and with them the dashboards and govbot load. `title` too, but only an
# empty one: a changed title is a real change (GA HR13's title fix).
GUARDED_FIELDS = (
    "title",
    "sponsorships",
    "actions",
    "versions",
    "documents",
    "abstracts",
    "other_titles",
    "subject",
    "sources",
)

# Guard (c) fires for a field when more than this share of the bills that had it
# last night have it empty tonight, among at least this many bills (so a field
# few bills have doesn't fire on a handful of real removals). Measured over every
# raw scrape of KY, GA, WY, MT, TN, IL, CA and NH (25 Nov 2026): among night/field
# losses on 20+ bills, every real scraper failure lost 69-100% of the field and
# everything else under 20%, nothing in between.
FIELD_REGRESSION_THRESHOLD = (0.5, 20)  # (share of the bills that had it, minimum bills)

KEPT_FILE = "kept_empty_fields.json"
REGRESSION_FILE = "field_regressions.json"


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _write_or_remove(path: Path, content: Any) -> None:
    """Write `content` (sorted, so the same night gives the same bytes), or remove
    the file when there's nothing to report."""
    if not content:
        if path.exists():
            path.unlink()
        return
    text = json.dumps(content, indent=2, sort_keys=True) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class BillGuards:
    """One run's guards. Make one per run, pass it to every handle_bill call,
    then call finish()."""

    def __init__(self, errors_folder: Path, state: str, first_seen: Optional[str]) -> None:
        self.state = state
        self.kept_path = Path(errors_folder) / KEPT_FILE
        self.regression_path = Path(errors_folder) / REGRESSION_FILE
        # The scrape's commit time names the night, so a re-run of the same
        # scrape writes the same files.
        self.night = first_seen
        try:
            self.kept: dict[str, dict] = json.loads(self.kept_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.kept = {}
        self.had: Counter = Counter()
        self.lost: Counter = Counter()  # also the bills kept tonight, per field

    def keep_nonempty(self, bill_key: str, previous: dict[str, Any], data: dict[str, Any]) -> list[str]:
        """Guard (a), in place on `data` (tonight's bill). Returns the fields kept
        from `previous` (the bill's metadata.json). Also counts, per field, the
        bills that had it and the ones that lost it tonight, for guard (c)."""
        kept = []
        for field in GUARDED_FIELDS:
            if is_empty(previous.get(field)):
                continue
            self.had[field] += 1
            if is_empty(data.get(field)):
                self.lost[field] += 1
                data[field] = previous[field]
                kept.append(field)

        before = self.kept.get(bill_key, {})
        entry = {field: {"first_kept": (before.get(field) or {}).get("first_kept", self.night)} for field in kept}
        if entry:
            self.kept[bill_key] = entry
        else:
            self.kept.pop(bill_key, None)  # every field came back (or never left)
        return kept

    def regressions(self) -> list[dict[str, Any]]:
        """Guard (c): one entry per field over the threshold."""
        share, min_bills = FIELD_REGRESSION_THRESHOLD
        return [
            {
                "state": self.state,
                "night": self.night,
                "field": field,
                "bills_lost": self.lost[field],
                "bills_had": self.had[field],
            }
            for field in GUARDED_FIELDS
            if self.had[field] >= min_bills and self.lost[field] > share * self.had[field]
        ]

    def finish(self) -> dict[str, Any]:
        """Write the two files and print the night's warnings. Returns
        {"kept": {field: bills kept tonight}, "regressions": [...]}."""
        _write_or_remove(self.kept_path, self.kept)
        for field, n in sorted(self.lost.items()):
            print(
                f"⚠️ Kept last night's {field} on {n} bills: tonight's scrape had it empty "
                f"(see .windycivi/errors/{KEPT_FILE})"
            )

        found = self.regressions()
        for r in found:
            print(
                f"::warning::Scraper regression? {r['field']} is empty tonight on {r['bills_lost']} of the "
                f"{r['bills_had']} {r['state'].upper()} bills that had it. Last night's values were kept."
            )
        _write_or_remove(self.regression_path, found)
        return {"kept": dict(self.lost), "regressions": found}
