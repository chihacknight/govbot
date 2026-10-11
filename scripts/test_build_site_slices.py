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
    run_downloads(data)


def run_downloads(data):
    import csv, io, json, zipfile
    data = dict(data, bills=data["bills"] + [
        bill("wy", "SF3", "2026-02-02", sponsors=("=HYPERLINK(\"x\")", "Señora Núñez")),
        dict(bill("il", "HB 9", "2026-03-03"), session="104th", title="-5% tax", tags=["housing"]),
    ])
    d = m.build_downloads(data)
    assert set(d) == {"bills-il.csv", "bills-wy.csv", "govbot-bills-all.csv.zip", "README.txt",
                      "manifest.json"}, set(d)

    raw = d["bills-wy.csv"]
    assert raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM so Excel shows accents"
    assert b"\r\n" in raw, "CRLF line endings"
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[0] == m.CSV_COLUMNS
    assert [r[3] for r in rows[1:]] == ["SF1", "SF2", "SF3"], "sorted by session then bill"
    sf3 = rows[3]
    assert sf3[0] == "wy" and sf3[1] == "Wyoming" and sf3[8] == "'=HYPERLINK(\"x\"); Señora Núñez", sf3
    assert sf3[6] == "2026-02-02" and sf3[10] == "https://x/SF3"

    il = list(csv.reader(io.StringIO(d["bills-il.csv"].decode("utf-8-sig"))))
    hb9 = next(r for r in il if r[3] == "HB 9")
    assert hb9[4] == "'-5% tax", "a formula-like title is neutralised in the CSV"
    assert hb9[9] == "housing"
    assert hb9[11] == m.SITE + "dashboard/legislation.html#bill=il~104th~HB%209", hb9[11]
    assert m.bill_key({"state": "il", "session": "2025-2026", "id": "SB 1 (a)"}) == "il~2025-2026~SB%201%20(a)"

    z = zipfile.ZipFile(io.BytesIO(d["govbot-bills-all.csv.zip"]))
    assert z.namelist() == ["govbot-bills-all.csv", "README.txt"]
    every = list(csv.reader(io.StringIO(z.read("govbot-bills-all.csv").decode("utf-8-sig"))))
    assert len(every) == 1 + len(data["bills"]) and [r[0] for r in every[1:]][:5] == ["il"] * 5
    assert "CC BY 4.0" in d["README.txt"].decode() and "Sponsors" in d["README.txt"].decode()
    assert m.build_downloads(data) == d, "same data, same bytes (the zip has a fixed timestamp)"

    man = json.loads(d["manifest.json"])
    assert man["total_rows"] == len(data["bills"]) and man["license"] == "CC BY 4.0"
    assert {f["jurisdiction"]: f["rows"] for f in man["jurisdictions"]} == {"il": 5, "wy": 3}
    assert all(f["bytes"] == len(d[f["file"]]) for f in man["jurisdictions"])
    print("ok - build_downloads: all assertions passed")


if __name__ == "__main__":
    run()
