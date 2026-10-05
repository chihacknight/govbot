#!/usr/bin/env python3
"""Offline tests for build_bill_summaries.py — no network, no pdftotext.

The per-state extractors run against REAL official summary documents (captured
with ``pdftotext -layout`` / HTML-to-text in scripts/__snapshots__/bill_summaries/;
each file's first line is a provenance comment: title | document note | URL), and
the build loop against injected fetchers so keying, the wrong-bill guard, capping,
round-robin and every fail-soft path run deterministically.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bill_summaries as m  # noqa: E402

FIX = Path(__file__).resolve().parent / "__snapshots__" / "bill_summaries"


def doc(name):
    """A snapshot's document text (minus the provenance comment line)."""
    return (FIX / f"{name}.txt").read_text().split("\n", 1)[1]


def run():
    # --- Michigan: HFA "SUMMARY:" and SFA "CONTENT" ---------------------------
    s = m.extract_mi(doc("mi_HB6302"))
    assert s.startswith("House Bill 6302 would amend provisions of the Revised School Code"), s
    assert "FISCAL IMPACT" not in s and "MCL" not in s and "Allegiance. 1" not in s, s
    s = m.extract_mi(doc("mi_SB1136"))
    assert s.startswith("The bill would amend the Publicly Funded Health Insurance Contribution Act"), s
    assert "\n• Beginning January 1, 2027" in s, "SFA '--' bullets become their own '•' lines"
    assert len(s) <= m._MAX_LEN, "long summaries are trimmed"
    s = m.extract_mi(doc("mi_HB6130"))
    assert "Community District Education Trust Fund" in s and "BACKGROUND" not in s, s

    # --- Tennessee: fiscal note "SUMMARY OF BILL:" ----------------------------
    s = m.extract_tn(doc("tn_SB2318"))
    assert s == ("Authorizes a private postsecondary institution, including one that is religiously "
                 "affiliated, to establish a public charter school."), s

    # --- Idaho: Statement of Purpose (routing-slip line dropped) --------------
    s = m.extract_id(doc("id_H0963"))
    assert s.startswith("This legislation clarifies the definition of a quorum for HOA meetings."), s
    assert "RS33713" not in s and "FISCAL NOTE" not in s, s

    # --- Louisiana: abstract, résumé digest "New law", resolution -------------
    la492 = doc("la_HB492")
    title492 = "DWI: Creates the Governor's Task Force on Impaired Driving (EN SEE FISC NOTE GF EX)"
    assert m.extract_la(la492, title492).startswith(
        "Creates the Governor's Task Force on Impaired Driving to reduce impaired driving"), \
        "an abstract that adds to the title is used"
    s = m.extract_la(la492, "Creates the Governor's Task Force on Impaired Driving to reduce "
                            "impaired driving incidents and related fatalities")
    assert s.startswith("Proposed law creates the Governor's Task Force"), \
        "an abstract that only restates the title gives way to the 'Proposed law' paragraphs"
    s = m.extract_la(doc("la_HB302"))
    assert s.startswith("New law prohibits, when there is a municipal or parish ordinance"), s
    assert "Existing law" not in s and "(Adds" not in s, s
    s = m.extract_la(doc("la_HR317"))
    assert s.startswith("Urges and requests that the Dept. of Transportation and Development"), s

    # --- the wrong-bill guard -------------------------------------------------
    assert m.mentions_bill(doc("mi_HB5317"), "HB 5317")          # "H.B. 5317"
    assert m.mentions_bill(doc("mi_HB6302"), "HB 6302")          # "House Bill 6302"
    assert m.mentions_bill(doc("tn_SB2318"), "SB 2318")          # "HB 2000 - SB 2318"
    assert m.mentions_bill(doc("id_HJM021"), "HJM 21")           # "RS33714 / HJM021"
    assert m.mentions_bill(doc("la_HB302"), "HB302")             # "ACT 792 (HB 302)"
    assert not m.mentions_bill(doc("tn_HB1881"), "HB 1881"), \
        "Open States linked HB 1881 to SB 1585's fiscal note — must be rejected"
    assert not m.mentions_bill("House Bill 14301 would", "HB 4301"), "no partial-number match"

    # --- document picking -----------------------------------------------------
    meta = {"documents": [
        {"note": "SUMMARY OF BILL REPORTED FROM COMMITTEE", "links": [{"url": "https://x/sfa.pdf"}]},
        {"note": "Summary as Introduced (5/1/2025)", "links": [
            {"url": "https://x/hla.pdf", "media_type": "application/pdf"},
            {"url": "https://x/hla.htm", "media_type": "text/html"}]}]}
    assert m.pick_document("mi", meta) == ("Summary as Introduced (5/1/2025)", "https://x/hla.htm"), \
        "preferred note wins, HTML preferred over PDF"
    assert m.pick_document("tn", {"documents": [{"note": "Fiscal Memo for HA1", "links": [{"url": "u"}]}]}) is None
    assert m.pick_document("id", {}) is None

    # --- keying matches the frontend's billKey --------------------------------
    assert m.bill_key("mi", "2025-2026", "HB 4301") == "mi~2025-2026~HB%204301"
    assert m.govbot_meta_url("mi", "2025-2026", "HB 4301", "https://raw.example/g") == \
        "https://raw.example/g/mi-legislation/main/country:us/state:mi/sessions/2025-2026/bills/HB4301/metadata.json"

    # --- build loop with injected fetchers ------------------------------------
    data = {"bills": [
        {"state": "tn", "session": "114", "id": "SB 2318", "latest_action": "2026-03-01"},
        {"state": "tn", "session": "114", "id": "HB 1881", "latest_action": "2026-03-02"},  # wrong doc
        {"state": "tn", "session": "114", "id": "HB 9", "latest_action": "2026-03-03"},     # no doc
        {"state": "la", "session": "2026", "id": "HB302", "latest_action": "2026-01-01"},
        {"state": "ca", "session": "2025", "id": "AB 1", "latest_action": "2026-09-01"},    # not covered
    ]}
    docs = {"SB2318": "tn_SB2318", "HB1881": "tn_HB1881", "HB302": "la_HB302"}

    def fake_json(url):
        bid = url.split("/bills/")[1].split("/")[0]
        if bid not in docs:
            return {"documents": []}
        note = "Fiscal Note" if bid != "HB302" else "Resume Digest for HB302"
        return {"documents": [{"note": note, "links": [{"url": "doc://" + bid}]}]}

    def fake_text(url):
        return doc(docs[url.replace("doc://", "")])

    cache, added, attempted = m.build(data, {}, cap=10, fetch_json=fake_json, fetch_text=fake_text)
    tn, la = cache["tn"], cache["la"]
    assert tn["tn~114~SB%202318"][0].startswith("Authorizes a private postsecondary"), tn
    assert tn["tn~114~SB%202318"][1] == "doc://SB2318", "the source document URL is kept for lineage"
    assert tn["tn~114~HB%201881"] == ["", ""], "a mismatched document is cached empty, not used"
    assert tn["tn~114~HB%209"] == ["", ""], "no summary document -> cached empty"
    assert la["la~2026~HB302"][0].startswith("New law prohibits"), la
    assert "ca" not in cache and added == 2 and attempted == 4, (added, attempted)

    # --- cap + round-robin: one state can't take the whole cap ----------------
    c2, _a, t2 = m.build(data, {}, cap=2, fetch_json=fake_json, fetch_text=fake_text)
    assert t2 == 2 and len(c2["tn"]) == 1 and len(c2["la"]) == 1, "round-robin across states"
    c2, _a, t3 = m.build(data, c2, cap=10, fetch_json=fake_json, fetch_text=fake_text)
    assert t3 == 2, "a re-run only attempts the still-uncached bills"

    # --- fail-soft: transient failures are left uncached to retry -------------
    def boom(url):
        raise RuntimeError("503")
    c3, a3, _t = m.build(data, {}, cap=10, fetch_json=boom, fetch_text=fake_text)
    assert c3 == {"mi": {}, "tn": {}, "id": {}, "la": {}} and a3 == 0, "metadata outage -> nothing cached"
    c4, _a, _t = m.build(data, {}, cap=10, fetch_json=fake_json, fetch_text=lambda u: "")
    assert "tn~114~SB%202318" not in c4["tn"], "empty extraction (poppler down) is transient"

    print("ok - build_bill_summaries: all assertions passed")


if __name__ == "__main__":
    run()
