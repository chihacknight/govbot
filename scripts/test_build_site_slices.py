#!/usr/bin/env python3
"""Offline tests for build_site_slices.py — slices are derived correctly from data.json."""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site_slices as m  # noqa: E402


def bill(state, bid, when, tags=(), sponsors=("A Person",)):
    return {"state": state, "session": "2026", "id": bid, "title": "T " + bid, "chamber": "lower",
            "latest_action": when, "latest_action_desc": "did " + bid, "sponsors": list(sponsors),
            "url": "https://x/" + bid, "tags": list(tags)}


def run():
    data = {
        "generated_at": "2026-10-01T00:00:00Z", "source": "test",
        "states": [{"code": "il", "name": "Illinois"}, {"code": "wy", "name": "Wyoming"}],
        "empty_jurisdictions": [], "tags": [{"name": "housing"}, {"name": "education"}],
        "bills": [
            bill("il", "HB1", "2026-09-30", ["housing"]),
            bill("il", "HB2", "2026-01-02"),            # older than the IL window
            bill("il", "HB3", "2026-09-01", ["education", "nope"]),
            bill("il", "HB4", "2026-08-01"),
            bill("wy", "SF1", ""),                      # no recorded action
            bill("wy", "SF2", "2026-05-05"),
        ],
    }
    s = m.build_slices(data, recent=2, il_days=200, today=dt.date(2026, 10, 1))
    assert set(s) == {"index.json", "il.json", "wy.json", "il_recent.json", "search.json"}, set(s)

    idx = s["index.json"]
    assert idx["counts"] == {"il": 4, "wy": 2}
    assert [b["id"] for b in idx["recent"]["il"]] == ["HB1", "HB3"], "newest first, capped at --recent"
    assert [b["id"] for b in idx["recent"]["wy"]] == ["SF2"], "bills without an action are not 'recent'"
    assert idx["recent"]["il"][0]["url"] == "https://x/HB1", "recent rows are full records (the modal needs them)"
    assert idx["states"] == data["states"] and idx["tags"] == data["tags"]

    assert len(s["il.json"]["bills"]) == 4 and len(s["wy.json"]["bills"]) == 2
    assert [b["id"] for b in s["il_recent.json"]["bills"]] == ["HB1", "HB3", "HB4"], "last 200 days only"

    rows = s["search.json"]["bills"]
    assert rows[0] == ["il", "2026", "HB1", "T HB1", "A Person", [0]], rows[0]
    assert rows[2][5] == [1], "unknown tags are dropped, known ones become ids"
    assert s["search.json"]["tags"] == ["housing", "education"]
    print("ok - build_site_slices: all assertions passed")


if __name__ == "__main__":
    run()
