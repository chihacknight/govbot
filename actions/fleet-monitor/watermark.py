"""Per-repo watermark store: the last workflow-run id shipped to Loki, per repo.

The log harvester is incremental — each hourly sweep must ship only runs it hasn't
shipped before. The watermark is the boundary: a JSON map of ``"<org>/<repo>"`` →
the highest completed run id already harvested. A run is new when its id exceeds
that. Run ids are monotonic in creation order, so the id alone orders runs without
a second field.

Backing store is deliberately a plain JSON file. In CI it is persisted between
hourly sweeps by the Actions cache (restore before the sweep, save after); for
local development it is just a file on disk. A missing file reads as ``{}`` — no
watermark for any repo — which the harvester turns into a bounded one-day
look-back rather than re-shipping a repo's entire history. That makes a lost cache
self-healing: the next sweep recovers the last day and moves on.
"""

import json
from pathlib import Path


def load_watermarks(path) -> dict:
    """Read the watermark map. A missing or empty file reads as ``{}`` so a cold
    start or a lost cache is a bounded look-back, never a crash."""
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text().strip()
    return json.loads(text) if text else {}


def save_watermarks(path, watermarks) -> None:
    """Write the watermark map (sorted keys, trailing newline) so a committed or
    cached file diffs cleanly between sweeps. The parent directory is created if
    absent — the workflow points this at a cached directory that may not exist on
    a cold run."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(watermarks, sort_keys=True, indent=2) + "\n")
