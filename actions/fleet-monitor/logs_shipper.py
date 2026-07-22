"""Encode labeled log batches into a Grafana Cloud Loki push payload.

Transport is the Loki push endpoint (``https://<stack>.grafana.net/loki/api/v1/push``):
one JSON body, no client library. The payload is a list of *streams*, each a set of
labels plus its timestamped log lines:

    {"streams": [
        {"stream": {"org", "state", "workflow", "outcome"},
         "values": [["<epoch-ns>", "<line>", {"run_id", "run_url"}], ...]}
    ]}

Labels are capped at ``org``/``state``/``workflow``/``outcome`` by design — the same
cardinality discipline the metrics shipper applies. Run and job identifiers are high
cardinality, so they never become labels: they ride in each entry's third element,
Loki *structured metadata*, queryable without exploding the stream count. The
README's Budgets section is the single source of the log-volume arithmetic against
the 50 GB/month free-tier budget.

Pure function of its inputs — the same batches always produce a byte-identical
payload (snapshot-tested). Streams and the values within them are sorted, and the
JSON is compact with sorted keys, so the bytes are deterministic. Resilient per
batch the way the metrics shipper is per record: a batch that can't be encoded (a
control character in a label, a missing key) is skipped rather than aborting the
push, and a batch with no entries emits no stream — absence marks the gap.
"""

import json

# Labels a log stream may carry. Anything higher-cardinality (run id, job, sha)
# travels in structured metadata on the entry, never as a label.
STREAM_LABELS = ("org", "state", "workflow", "outcome")


def _check_label(value: str) -> str:
    """A label value with no control characters. A newline in a label would break
    the stream identity Loki derives from the label set, so it fails loudly rather
    than being silently mangled — mirroring the metrics shipper's tag guard."""
    value = str(value)
    if any(c in value for c in "\n\r"):
        raise ValueError(f"control character in log label value {value!r}")
    return value


def _stream(batch) -> dict:
    """One Loki stream from a labeled batch. Raises (KeyError on a missing label,
    ValueError on a bad label value) so the caller can isolate it per batch."""
    labels = {name: _check_label(batch["labels"][name]) for name in STREAM_LABELS}
    values = []
    for entry in sorted(batch["entries"], key=lambda e: e["timestamp_ns"]):
        value = [str(int(entry["timestamp_ns"])), entry["line"]]
        metadata = entry.get("metadata")
        if metadata:
            # Loki structured metadata values must be strings.
            value.append({k: str(v) for k, v in metadata.items()})
        values.append(value)
    return {"stream": labels, "values": values}


def encode_logs(batches) -> str:
    """Return the Loki push payload (compact JSON) for a list of labeled batches.

    Deterministic: streams are sorted by their label set and each stream's values
    by timestamp, so identical batches yield byte-identical output. A batch that
    can't be encoded is skipped, and an empty batch contributes no stream.
    """
    streams = []
    for batch in batches:
        try:
            stream = _stream(batch)
        except (KeyError, TypeError, ValueError):
            # KeyError: a missing label or entry key. ValueError: a control
            # character in a label. TypeError: a non-int timestamp. One bad
            # batch is skipped, never a half-built stream, never an aborted push.
            continue
        if stream["values"]:
            streams.append(stream)
    streams.sort(key=lambda s: sorted(s["stream"].items()))
    return json.dumps({"streams": streams}, sort_keys=True, separators=(",", ":"))
