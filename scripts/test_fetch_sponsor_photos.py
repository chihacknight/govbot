#!/usr/bin/env python3
"""Offline tests for fetch_sponsor_photos.py — no network, no real photos.

Runs with a synthetic Open States people checkout, a synthetic data.json, and
an injected fetcher, so it exercises selection, name resolution, manifest
keying, and every fail-soft path deterministically.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sponsor_photos as fsp  # noqa: E402


def _write_people(root):
    """A tiny people tree: al has an ambiguous surname (two Butlers) and one
    legislator with no image; ak has one clean legislator with an image."""
    def person(state, fname, given, family, full, image):
        d = root / "data" / state / "legislature"
        d.mkdir(parents=True, exist_ok=True)
        doc = {"name": full, "given_name": given, "family_name": family}
        if image is not None:
            doc["image"] = image
        (d / (fname + ".yml")).write_text(json.dumps(doc), encoding="utf-8")

    person("al", "greg-albritton", "Greg", "Albritton", "Greg Albritton",
           "https://img.example/greg.jpg")
    person("al", "mack-butler", "Mack", "Butler", "Mack Butler",
           "https://img.example/mack.png")
    person("al", "tom-butler", "Tom", "Butler", "Tom Butler",
           "https://img.example/tom.jpg")
    person("al", "no-photo", "Nora", "Noimage", "Nora Noimage", None)
    person("ak", "alyse-galvin", "Alyse", "Galvin", "Alyse Galvin",
           "https://img.example/alyse.webp")


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        people = root / "people"
        _write_people(people)
        out_dir = root / "out"
        manifest = root / "legislator_images.json"

        index = fsp.build_index(str(people))
        assert "al" in index and "ak" in index, "index missing states"

        # --- matcher rules --------------------------------------------------
        assert fsp.match("al", "Albritton", index)[1] == "Greg Albritton", "surname-only"
        assert fsp.match("al", "Greg Albritton", index)[1] == "Greg Albritton", "first last"
        assert fsp.match("al", "Butler", index) is None, "ambiguous surname must not resolve"
        assert fsp.match("al", "Butler, T", index)[1] == "Tom Butler", "disambiguate by initial"
        assert fsp.match("ak", "Galvin", index)[1] == "Alyse Galvin", "ak clean match"

        # --- on-screen selection: one bill per state, newest first ---------
        bills = [
            {"state": "al", "latest_action": "2026-02-10", "sponsors": ["Albritton"]},
            {"state": "al", "latest_action": "2026-01-01", "sponsors": ["Butler"]},   # 2nd al bill -> dropped
            {"state": "ak", "latest_action": "2026-02-09", "sponsors": ["Galvin", "Noimage"]},
            {"state": "al", "latest_action": None, "sponsors": ["Butler"]},
        ]
        picked = fsp.onscreen_bills(bills, per_state=1, max_bills=6)
        assert [b["latest_action"] for b in picked] == ["2026-02-10", "2026-02-09"], \
            f"one-per-state newest-first failed: {picked}"

        # --- vendor with an injected fetcher -------------------------------
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if "tom" in url:            # simulate a download failure -> fall back to monogram
                raise RuntimeError("boom")
            return b"\xff\xd8\xff" + url.encode()  # non-empty pseudo-bytes

        got, wanted = fsp.vendor(bills, index, out_dir, manifest, fetch=fake_fetch,
                                 per_state=1, max_bills=6)

        data = json.loads(manifest.read_text())
        # Greg (al) + Alyse (ak) resolve with a photo; Butler is ambiguous (2nd
        # bill dropped anyway) and Noimage has no image URL -> neither appears.
        assert set(data.keys()) == {"al:greg albritton", "ak:alyse galvin"}, \
            f"manifest keys wrong: {sorted(data)}"
        assert data["al:greg albritton"] == "assets/legislators/al-greg-albritton.jpg"
        assert data["ak:alyse galvin"] == "assets/legislators/ak-alyse-galvin.webp"
        assert (out_dir / "al-greg-albritton.jpg").exists()
        assert (out_dir / "ak-alyse-galvin.webp").exists()
        assert got == 2, f"expected 2 downloaded, got {got}"

        # --- fail-soft: empty index writes an empty manifest, no crash -----
        m2 = root / "empty.json"
        got2, wanted2 = fsp.vendor(bills, {}, root / "out2", m2, fetch=fake_fetch)
        assert got2 == 0 and json.loads(m2.read_text()) == {}, "empty index should yield {}"

        # --- fail-soft: a sponsor whose photo URL 404s is simply skipped ----
        bills3 = [{"state": "al", "latest_action": "2026-03-01", "sponsors": ["Butler, T"]}]
        got3, wanted3 = fsp.vendor(bills3, index, root / "out3", root / "m3.json",
                                   fetch=fake_fetch)
        assert wanted3 == 1 and got3 == 0, "a failed download must not be manifested"
        assert json.loads((root / "m3.json").read_text()) == {}, "no entry for failed fetch"

    print("ok - fetch_sponsor_photos: all assertions passed")


if __name__ == "__main__":
    run()
