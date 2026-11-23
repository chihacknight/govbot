"""Send one workflow's events to Vector and wait for its Loki acknowledgement."""

import json
import urllib.error
import urllib.request

VECTOR_URL = "http://127.0.0.1:8687/logs"


def push_to_vector(batches):
    body = "\n".join(
        json.dumps({
            "labels": batch["labels"],
            "timestamp_ns": entry["timestamp_ns"],
            "message": entry["line"],
            "metadata": entry.get("metadata", {}),
        }, ensure_ascii=False)
        for batch in batches
        for entry in batch["entries"]
    ).encode("utf-8")
    request = urllib.request.Request(
        VECTOR_URL, data=body, headers={"Content-Type": "application/x-ndjson"},
    )
    # Vector owns retries. A caller-side retry could replay already accepted batches.
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            if response.status != 200:
                raise RuntimeError(f"Vector returned unexpected HTTP {response.status}")
    except urllib.error.HTTPError as error:
        error.close()
        raise RuntimeError(f"Vector did not acknowledge delivery (HTTP {error.code})") from error
    except OSError as error:
        raise RuntimeError(f"Vector acknowledgement unavailable ({type(error).__name__})") from error


def push_heartbeat(now):
    push_to_vector([{
        "labels": {"service": "fleet-logs"},
        "entries": [{
            "timestamp_ns": int(now.timestamp()) * 1_000_000_000,
            "line": "Fleet log sweep complete",
        }],
    }])
