"""Offline checks for set_repo_metadata.py: python3 .github/data-repo-setup/test_set_repo_metadata.py"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import set_repo_metadata as m  # noqa: E402

assert len(m.JURISDICTIONS) == 56, len(m.JURISDICTIONS)
topic_ok = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
for code in m.JURISDICTIONS:
    assert topic_ok.match(m.JURISDICTIONS[code][1]), code
    assert len(m.description(code)) <= 350, code
    assert "Frankie" not in m.description(code)
assert all(topic_ok.match(t) for t in m.SHARED_TOPICS)
assert len(m.SHARED_TOPICS) + 1 + 2 <= 20  # GitHub allows 20 topics; the pipeline adds 2 of its own

fresh = {"description": m.placeholder("il"), "homepage": "", "topics": ["govbot-scraper-paused", "govbot-session-out"]}
p = m.plan("il", fresh)
assert p["description"].startswith("Illinois legislation") and p["homepage"] == m.HOMEPAGE
assert "illinois" in p["add_topics"] and not any(t.startswith("govbot-s") for t in p["add_topics"])

done = {"description": m.description("il"), "homepage": m.HOMEPAGE, "topics": m.SHARED_TOPICS + ["illinois", "govbot-session-in"]}
assert m.plan("il", done) == {}, "a second run changes nothing"

custom = {"description": "Written by hand", "homepage": "https://example.org", "topics": []}
assert "description" not in m.plan("il", custom) and "homepage" not in m.plan("il", custom)
print("ok")
