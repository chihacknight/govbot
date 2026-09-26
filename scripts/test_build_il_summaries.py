#!/usr/bin/env python3
"""Offline tests for build_il_summaries.py — no network, no pdftotext.

The synopsis parser is exercised against REAL extracted Illinois bill text
(captured in scripts/__snapshots__/il_fulltext/), and the build loop against
injected fetchers so selection, keying, capping, and every fail-soft path run
deterministically.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_il_summaries as m  # noqa: E402

FIX = Path(__file__).resolve().parent / "__snapshots__" / "il_fulltext"


def run():
    # --- extract_synopsis against real IL full text -----------------------
    sb = (FIX / "il_SB3578.txt").read_text()
    syn = m.extract_synopsis(sb)
    assert syn.startswith("Creates the Data Center Construction by Foreign Adversaries Act."), \
        f"SB3578 synopsis wrong: {syn!r}"
    assert "New Act" not in syn, "the leading 'New Act' citation must be stripped"
    assert "SYNOPSIS" not in syn and "LRB" not in syn, "label/footer must not leak in"
    assert "foreign adversary" in syn, "synopsis prose should be kept whole"

    ilcs = (FIX / "il_ILCS_sample.txt").read_text()
    syn2 = m.extract_synopsis(ilcs)
    assert syn2 == "Repeals the Digital Asset Tax Act. Effective immediately.", \
        f"ILCS-run synopsis wrong: {syn2!r}"

    # --- edge cases -------------------------------------------------------
    assert m.extract_synopsis("") == "", "empty in -> empty out"
    assert m.extract_synopsis("A bill with no synopsis header at all.") == "", "no header -> none"
    # a bare citation run with no prose -> nothing worth showing
    assert m.extract_synopsis("SYNOPSIS AS INTRODUCED:\nNew Act\n\nLRB104 1 x") == "", \
        "citation-only synopsis -> empty"
    # stops at 'AN ACT' when there is no LRB footer
    syn3 = m.extract_synopsis("SYNOPSIS AS INTRODUCED:\nAmends the Vehicle Code. Does a thing "
                              "that is clearly described here.\nAN ACT concerning transportation.")
    assert syn3.startswith("Amends the Vehicle Code.") and "AN ACT" not in syn3, syn3
    # long synopsis is trimmed on a sentence boundary
    long = "SYNOPSIS AS INTRODUCED:\nNew Act\n" + ("Creates a thing. " * 120) + "\nLRB1 x"
    out = m.extract_synopsis(long)
    assert len(out) <= m._MAX_SYNOPSIS_LEN and out.endswith((".", "…")), "trim on boundary"

    # --- keying -----------------------------------------------------------
    assert m.bill_key("104th", "HB 10") == "il~104th~HB%2010"
    assert m.govbot_meta_url("104th", "HB 10", "https://raw.example/govbot-data") == \
        "https://raw.example/govbot-data/il-legislation/main/country:us/state:il/" \
        "sessions/104th/bills/HB10/metadata.json"

    # --- pdf link picking -------------------------------------------------
    meta_ok = {"versions": [{"links": [
        {"url": "https://ilga.gov/x.html", "media_type": "text/html"},
        {"url": "https://ilga.gov/10400HB0010.pdf", "media_type": "application/pdf"}]}]}
    assert m.pdf_link_from_meta(meta_ok) == "https://ilga.gov/10400HB0010.pdf"
    assert m.pdf_link_from_meta({"versions": []}) is None

    # --- build loop with injected fetchers --------------------------------
    data = {"bills": [
        {"state": "il", "session": "104th", "id": "SB3578", "url": "u1"},
        {"state": "il", "session": "104th", "id": "HB5798", "url": "u2"},
        {"state": "il", "session": "104th", "id": "HR9",    "url": "u3"},  # no PDF -> ""
        {"state": "ca", "session": "2025", "id": "AB1", "url": "u4"},      # not IL -> ignored
    ]}
    text_by_id = {"SB3578": sb, "HB5798": ilcs}

    def fake_json(url, timeout=25):
        # url ends with .../bills/<ID>/metadata.json
        bid = url.split("/bills/")[1].split("/")[0]
        if bid in text_by_id:
            return {"versions": [{"links": [{"url": "pdf://" + bid, "media_type": "application/pdf"}]}]}
        return {"versions": []}  # HR9: no PDF link

    def fake_bytes(url, timeout=45):
        return url.encode()  # "pdf://SB3578" -> bytes; pdf_text maps it back

    def fake_pdf_text(b):
        bid = b.decode().replace("pdf://", "")
        return text_by_id.get(bid, "")

    cache, added, attempted = m.build(m.il_bills(data), {}, cap=10,
                                      get_json=fake_json, get_bytes=fake_bytes,
                                      pdf_text=fake_pdf_text)
    assert m.bill_key("104th", "SB3578") in cache and cache[m.bill_key("104th", "SB3578")], "SB3578 summarized"
    assert cache[m.bill_key("104th", "HB5798")] == "Repeals the Digital Asset Tax Act. Effective immediately."
    assert cache[m.bill_key("104th", "HR9")] == "", "HR9 has no PDF -> cached empty (not retried)"
    assert m.bill_key("2025", "AB1") not in cache, "non-IL bills are ignored"
    assert added == 2 and attempted == 3, f"added/attempted wrong: {added}/{attempted}"

    # --- cap limits the work; a re-run resumes and skips cached -----------
    cache2, added2, attempted2 = m.build(m.il_bills(data), {}, cap=1,
                                         get_json=fake_json, get_bytes=fake_bytes,
                                         pdf_text=fake_pdf_text)
    assert attempted2 == 1 and len(cache2) == 1, "cap bounds one run"
    cache2, added2b, attempted2b = m.build(m.il_bills(data), cache2, cap=10,
                                           get_json=fake_json, get_bytes=fake_bytes,
                                           pdf_text=fake_pdf_text)
    assert attempted2b == 2, "the second run only attempts the still-uncached bills"

    # --- fail-soft: a metadata fetch that raises -> "" not a crash --------
    def boom_json(url, timeout=25):
        raise RuntimeError("503")
    cache3, added3, attempted3 = m.build([("104th", "HB1", "u")], {}, cap=10,
                                         get_json=boom_json, get_bytes=fake_bytes,
                                         pdf_text=fake_pdf_text)
    assert cache3 == {} and added3 == 0, "a transient (raising) fetch is fail-soft AND left uncached to retry"

    # a bill whose PDF text can't be extracted (poppler missing) is transient too —
    # left uncached so it retries once poppler is back, never cached as empty.
    cache4, _a4, _t4 = m.build([("104th", "SB3578", "u")], {}, cap=10,
                               get_json=fake_json, get_bytes=fake_bytes,
                               pdf_text=lambda b: "")   # extractor yields nothing
    assert cache4 == {}, "empty extraction (poppler down) is transient, not cached"

    print("ok - build_il_summaries: all assertions passed")


if __name__ == "__main__":
    run()
