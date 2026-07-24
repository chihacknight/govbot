"""Per-(repo, workflow) watermark store: the last run id shipped to Loki.

The log harvester is incremental — each hourly sweep must ship only runs it hasn't
shipped before. The watermark is the boundary: a JSON map of
``"<org>/<repo>/<workflow>"`` → the highest completed run id already harvested for
that workflow. The key is per workflow, not per repo, because each workflow's run
stream is independent — see log_harvester's module docstring. A run is new when its
id exceeds its workflow's entry. Run ids are monotonic in creation order, so the id
alone orders runs without a second field.

Backing store is deliberately a plain JSON file. In CI it is persisted between
hourly sweeps by the Actions cache (restore before the sweep, save after); for
local development it is just a file on disk. A missing file reads as ``{}`` — no
watermark for any repo — which the harvester turns into a bounded one-day
look-back rather than re-shipping a repo's entire history. That makes a lost cache
self-healing: the next sweep recovers the last day and moves on.
"""

import json
import sys
from pathlib import Path


def load_watermarks(path) -> dict:
    """Read the watermark map. A missing, empty, or corrupt file reads as ``{}``
    so a cold start, a lost cache, or a truncated cache save is a bounded
    look-back, never a crash. Corruption matters because the workflow re-saves
    the cache after every run: a crash here would re-persist the corrupt file
    and stay red every hour, whereas an empty read self-heals on the next save."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text().strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(
            f"watermark file {p} is corrupt; starting empty (bounded look-back re-ship)",
            file=sys.stderr,
        )
        return {}


def save_watermarks(path, watermarks) -> None:
    """Write the watermark map (sorted keys, trailing newline) so a committed or
    cached file diffs cleanly between sweeps. The parent directory is created if
    absent — the workflow points this at a cached directory that may not exist on
    a cold run."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(watermarks, sort_keys=True, indent=2) + "\n")
