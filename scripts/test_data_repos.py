#!/usr/bin/env python3
"""Offline test for data_repos.py: which data repo holds a state's session."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_repos as d  # noqa: E402

repos = d.repo_map()
# A moved state: its old repo is in govbot-history, by its real name...
assert d.repo_for("il", "103rd") == "govbot-history/il-legislation-data", d.repo_for("il", "103rd")
# ...except a session with its own (seeded) pair, read there.
assert d.repo_for("il", "104th") == "govbot-data/il-104th"
# A running state keeps today's repo.
assert d.repo_for("oh", "136") == "govbot-data/oh-legislation"
# A session with its own pair; every other session of the state stays in the old repo.
assert d.repo_for("tx", "90R") == "govbot-data/tx-90r"
assert d.repo_for("tx", "89R") == "govbot-history/tx-legislation-data"
assert d.repo_for("zz", "1") is None
assert len(repos) == 56 and repos["tx"]["sessions"] == {"90R": "govbot-data/tx-90r"}
assert d.pair_key("ga", "2025_26") == "ga-2025_26" and d.pair_key("az", "58th 1st") == "az-58th-1st"

# The state of a cloned folder comes from its files, so session folders work too.
with tempfile.TemporaryDirectory() as tmp:
    for folder, st in (("tx-legislation", "tx"), ("tx-90r", "tx"), ("usa-legislation", "usa")):
        (Path(tmp) / folder / "country:us" / f"state:{st}").mkdir(parents=True)
        assert d.state_of_folder(Path(tmp) / folder) == st, folder
    (Path(tmp) / "wy-legislation").mkdir()
    assert d.state_of_folder(Path(tmp) / "wy-legislation") == "wy"  # empty clone: the name

print("ok - data_repos: all assertions passed")
