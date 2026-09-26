#!/usr/bin/env python3
"""Offline tests for fetch_sponsor_photos.py — no network, no real photos.

Runs with a synthetic Open States people checkout, a synthetic data.json, and
injected fetch/wiki functions, so it exercises selection, name resolution, the
two-source photo fallback, manifest keying, and every fail-soft path
deterministically.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sponsor_photos as fsp  # noqa: E402


def _write_people(root):
    """A tiny people tree: al has an ambiguous surname (two Butlers) and a
    legislator with no image; ak has a clean legislator with an image; az has a
    legislator whose Open States image will fail to download (so the Wikipedia
    fallback has to supply the photo)."""
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
    person("az", "fally-back", "Fally", "Back", "Fally Back",
           "https://osfail.example/back.jpg")  # this host "fails" in the fake fetch
    # A federal (Congress) member — dir is "us", data.json labels bills "usa".
    person("us", "carol-miller", "Carol", "Miller", "Carol D. Miller",
           "https://img.example/carol.jpg")


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        people = root / "people"
        _write_people(people)

        index = fsp.build_index(str(people))
        assert {"al", "ak", "az"} <= set(index), "index missing states"

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
            {"state": "az", "latest_action": "2026-02-08", "sponsors": ["Back"]},
        ]
        picked = fsp.onscreen_bills(bills, per_state=1, max_bills=6)
        assert [b["latest_action"] for b in picked] == \
            ["2026-02-10", "2026-02-09", "2026-02-08"], f"one-per-state newest-first failed: {picked}"

        # --- injected sources ----------------------------------------------
        def fake_fetch(url):
            if "osfail" in url or "/tom" in url:   # these hosts/images "fail"
                raise RuntimeError("boom")
            return b"\xff\xd8\xff" + url.encode()   # non-empty pseudo-bytes

        # The Wikipedia fallback only knows Fally Back (returns a .png thumb).
        def fake_wiki(state, full):
            if state == "az" and full == "Fally Back":
                return "https://wiki.example/back-thumb.png"
            return None

        got, wanted = fsp.vendor(bills, index, root / "out", root / "m.json",
                                 fetch=fake_fetch, wiki=fake_wiki, per_state=1, max_bills=6)
        data = json.loads((root / "m.json").read_text())
        # Greg + Alyse via Open States images; Fally Back via the Wikipedia
        # fallback (his OS image failed). Noimage has neither -> not pictured.
        assert set(data.keys()) == {"al:greg albritton", "ak:alyse galvin", "az:fally back"}, \
            f"manifest keys wrong: {sorted(data)}"
        assert data["az:fally back"] == "assets/legislators/az-fally-back.png", "wiki fallback ext"
        assert (root / "out" / "az-fally-back.png").exists(), "wiki fallback file written"
        assert got == 3, f"expected 3 downloaded, got {got}"

        # --- federal ("usa") sponsors: us dir aliased to usa, keyed by RAW name
        assert "usa" in index and "us" in index, "federal roster aliased to usa"
        bills_fed = [{"state": "usa", "latest_action": "2026-02-11",
                      "sponsors": ["Carol D. Miller"]}]
        fsp.vendor(bills_fed, index, root / "outf", root / "mf.json",
                   fetch=fake_fetch, wiki=fake_wiki)
        dataf = json.loads((root / "mf.json").read_text())
        assert dataf == {"usa:carol d. miller": "assets/legislators/usa-carol-d-miller.jpg"}, \
            f"federal manifest must key by RAW sponsor name: {dataf}"

        # --- federal Wikipedia guard: a congressional role, no state needed ---
        def gj(summary):
            return lambda url, timeout=15: summary
        fed_ok = {"type": "standard", "description": "American politician",
                  "extract": "Carol Miller is a U.S. Representative from West Virginia.",
                  "thumbnail": {"source": "https://wiki.example/carol.jpg"}}
        assert fsp.wiki_thumbnail("usa", "Carol D. Miller", get_json=gj(fed_ok)) \
            == "https://wiki.example/carol.jpg", "federal accepts a congressional role"
        fed_no = dict(fed_ok, extract="Carol Miller is a chef.")
        assert fsp.wiki_thumbnail("usa", "Carol D. Miller", get_json=gj(fed_no)) is None, \
            "federal without a congressional role -> refuse"

        # --- Wikipedia guard: accept only a confident legislator match ------
        def gj(summary):
            return lambda url, timeout=15: summary
        ok = {"type": "standard", "description": "American politician",
              "extract": "Jane Roe is a member of the Alabama House of Representatives.",
              "thumbnail": {"source": "https://wiki.example/jane.jpg"}}
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj(ok)) == "https://wiki.example/jane.jpg"
        # disambiguation page -> refuse
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj({"type": "disambiguation"})) is None
        # right role but wrong/absent state -> refuse (guards against a namesake)
        wrong_state = dict(ok, extract="A member of the Texas House of Representatives.")
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj(wrong_state)) is None
        # names the state but not a legislator -> refuse
        not_leg = {"type": "standard", "description": "Alabama chef",
                   "extract": "Jane Roe is a chef from Alabama.",
                   "thumbnail": {"source": "https://wiki.example/x.jpg"}}
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj(not_leg)) is None
        # a lookup that raises (no page / network) -> None, no crash
        def boom(url, timeout=15):
            raise RuntimeError("404")
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=boom) is None

        # --- Wikipedia SEARCH fallback: exact title misses, search finds the
        #     disambiguated page, and the same confidence gate still applies -----
        def gj_search(url, timeout=15):
            if "/search/page" in url:                       # the search step
                return {"pages": [{"key": "Jane_Roe_(politician)"}]}
            if "politician" in url:                         # the found page's summary
                return {"type": "standard", "title": "Jane Roe (politician)",
                        "extract": "Jane Roe is a member of the Alabama House of Representatives.",
                        "thumbnail": {"source": "https://wiki.example/jane-dab.jpg"}}
            raise RuntimeError("404")                        # exact "Jane_Roe" page 404s
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj_search) \
            == "https://wiki.example/jane-dab.jpg", "search fallback finds the disambiguated page"

        # a search hit about a *different* person (surname absent) is rejected
        def gj_wrongperson(url, timeout=15):
            if "/search/page" in url:
                return {"pages": [{"key": "John_Doe"}]}
            if "John_Doe" in url:
                return {"type": "standard", "title": "John Doe",
                        "extract": "John Doe is a member of the Alabama House of Representatives.",
                        "thumbnail": {"source": "https://wiki.example/john.jpg"}}
            raise RuntimeError("404")
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj_wrongperson) is None, \
            "a search hit whose surname doesn't match must be refused"

        # search=False disables the fallback (exact-title only)
        assert fsp.wiki_thumbnail("al", "Jane Roe", get_json=gj_search, search=False) is None, \
            "search=False -> exact title only"

        # --- hardened image validation --------------------------------------
        assert fsp.is_image_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x02\x03"), "jpeg magic"
        assert fsp.is_image_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00"), "png magic"
        assert fsp.is_image_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp magic"
        assert not fsp.is_image_bytes(b"<!DOCTYPE html><html>blocked</html>"), "html is not an image"
        assert not fsp.is_image_bytes(b""), "empty is not an image"

        # resolve_photo rejects a source that returns HTML (an image host that
        # 200s a block/login page) and falls through to the next source.
        def html_then_image(url):
            return (b"<html>Access Denied</html>" if "osfail" in url
                    else b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
        d, src = fsp.resolve_photo(
            "az", "Fally Back", "https://osfail.example/back.jpg",
            fetch=html_then_image,
            wiki=lambda s, f: "https://wiki.example/back.png",
            max_bytes=3_000_000)
        assert src == "https://wiki.example/back.png" and fsp.is_image_bytes(d), \
            "HTML from the OS image is rejected; the real image wins"

        # --- fail-soft: empty index writes an empty manifest ---------------
        got2, _ = fsp.vendor(bills, {}, root / "out2", root / "m2.json",
                             fetch=fake_fetch, wiki=fake_wiki)
        assert got2 == 0 and json.loads((root / "m2.json").read_text()) == {}, "empty index -> {}"

        # --- fail-soft: a sponsor with no working source is simply skipped --
        bills3 = [{"state": "al", "latest_action": "2026-03-01", "sponsors": ["Butler, T"]}]
        got3, wanted3 = fsp.vendor(bills3, index, root / "out3", root / "m3.json",
                                   fetch=fake_fetch, wiki=fake_wiki)  # tom OS fails, no wiki
        assert wanted3 == 1 and got3 == 0, "a sponsor with no source must not be manifested"
        assert json.loads((root / "m3.json").read_text()) == {}, "no entry when every source fails"

    print("ok - fetch_sponsor_photos: all assertions passed")


if __name__ == "__main__":
    run()
