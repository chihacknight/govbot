#!/usr/bin/env python3
"""Offline guard for the dashboard keyword taxonomy (scripts/dashboard_tags.json).

Focus: the "elections & voting" topic must not swallow unrelated bills that merely
mention "registration" (vehicle, business, firearm, sex-offender registration…),
while still catching genuine election/voter/ballot bills. The same include_keywords
list boosts govbot's embedding tagger, so keeping bare "registration" out of it
matters for both the embedding and the keyword-fallback paths.

Run: python3 scripts/test_dashboard_tags.py
"""

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bdd", HERE / "build_dashboard_data.py")
bdd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bdd)

COMPILED = bdd.compile_keyword_tags(str(HERE / "dashboard_tags.json"))


def tags_for(title, abstract=""):
    meta = {"title": title, "abstracts": [{"abstract": abstract}] if abstract else []}
    return bdd.keyword_tags_for(meta, COMPILED)


class ElectionsTagging(unittest.TestCase):
    NON_ELECTION = [
        "Motor vehicle registration renewal fees",
        "Business entity registration and annual reports",
        "Sex offender registration requirements",
        "Firearm owner registration",
        "Professional licensure and registration of nurses",
    ]
    ELECTION = [
        "Voter registration modernization act",
        "Expands early voting and mail-in ballots",
        "Redistricting commission reform",
        "An act concerning campaign finance disclosure",
        "Establishes ranked-choice voting for municipal elections",
    ]

    def test_registration_alone_is_not_elections(self):
        for t in self.NON_ELECTION:
            self.assertNotIn("elections & voting", tags_for(t),
                             f"{t!r} should not be tagged elections & voting")

    def test_genuine_election_bills_are_tagged(self):
        for t in self.ELECTION:
            self.assertIn("elections & voting", tags_for(t),
                          f"{t!r} should be tagged elections & voting")

    def test_no_bare_registration_keyword(self):
        # Guard against re-introducing the over-broad keyword in either config path.
        import json
        cfg = json.loads((HERE / "dashboard_tags.json").read_text())
        kws = cfg["tags"]["elections & voting"]["include_keywords"]
        self.assertNotIn("registration", kws)
        self.assertIn("voter registration", kws)


if __name__ == "__main__":
    unittest.main(verbosity=2)
