"""Integration test for the production Vector config against a local fake Loki."""

import gzip
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import click

import main
from watermark import load_watermarks

HERE = Path(__file__).resolve().parent
WORKFLOW = "govbot-data/ms-legislation/extract-text.yml"
OTHER = "govbot-data/wi-legislation/scrape.yml"


class FakeLoki(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.path == "/loki/api/v1/push"
        body = gzip.decompress(self.rfile.read(int(self.headers["Content-Length"])))
        streams = json.loads(body)["streams"]
        self.server.requests.append((len(body), streams))
        reject = self.server.reject and any(
            stream["stream"].get("state") == "ms" and
            any("late" in entry[1] for entry in stream["values"])
            for stream in streams
        )
        self.send_response(429 if reject or len(body) >= 1_000_000 else 204)
        self.end_headers()

    def log_message(self, *_args):
        pass


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


class VectorDeliveryTest(unittest.TestCase):
    def test_batches_acknowledgements_and_watermarks(self):
        workflow_file = HERE.parents[1] / ".github/workflows/fleet-logs.yml"
        image = re.search(r"^  VECTOR_IMAGE: (\S+)$", workflow_file.read_text(), re.M)[1]
        with ThreadingHTTPServer(("", 0), FakeLoki) as loki, tempfile.TemporaryDirectory() as tmp:
            loki.requests = []
            loki.reject = True
            thread = Thread(target=loki.serve_forever, daemon=True)
            thread.start()
            host_mapping = ("--add-host", "host.docker.internal:host-gateway") if sys.platform == "linux" else ()
            try:
                container = docker(
                    "run", "--detach", *host_mapping, "--publish", "127.0.0.1::8687",
                    "--mount", f"type=bind,source={HERE}/vector.yaml,target=/etc/vector/vector.yaml,readonly",
                    "--env", f"LOKI_ENDPOINT=http://host.docker.internal:{loki.server_port}",
                    "--env", "GRAFANA_LOGS_USER=fixture", "--env", "GRAFANA_LOGS_KEY=fixture",
                    image, "--config", "/etc/vector/vector.yaml",
                    "--dangerously-allow-env-var-interpolation",
                )
                try:
                    address = docker("port", container, "8687/tcp")
                    url = f"http://{address}/logs"
                    for _ in range(50):
                        try:
                            with urlopen(url, timeout=1):
                                break
                        except HTTPError as error:
                            error.close()
                            break
                        except OSError:
                            time.sleep(0.2)
                    else:
                        self.fail("Vector did not start")
                    with patch("vector_push.VECTOR_URL", url):
                        self.check_delivery(loki, Path(tmp) / "logs.json")
                except Exception:
                    print(docker("logs", container), file=sys.stderr)
                    raise
                finally:
                    docker("rm", "--force", container)
            finally:
                loki.shutdown()
                thread.join()

    def check_delivery(self, loki, watermark):
        now = datetime.now(timezone.utc)
        timestamp_ns = int(now.timestamp()) * 1_000_000_000
        metadata = {"run_id": "42", "event_time": "2026-09-30T16:00:00Z"}

        def batch(key, state, lines):
            return {
                "watermark_key": key,
                "labels": {"state": state, "org": "govbot-data",
                           "workflow": key.rsplit("/", 1)[1], "outcome": "failure"},
                "entries": [
                    {"timestamp_ns": timestamp_ns + index, "line": line, "metadata": metadata}
                    for index, line in enumerate(lines)
                ],
            }

        early = "early " + "é" * 1500
        late = "late " + "é" * 1500
        lines = [early] * 250 + [late] * 250
        failed_batch = batch(WORKFLOW, "ms", lines)
        other_batch = batch(OTHER, "wi", ["other"])
        candidate = {WORKFLOW: 42, OTHER: 42}

        def sweep(batches):
            with patch.object(main, "_log_sources", return_value=([], None, None)), patch.object(
                main, "harvest_logs", return_value=(batches, candidate, [])
            ):
                return main._collect_logs(None, None, watermark, False, now, (), via_vector=True)

        with self.assertRaisesRegex(click.ClickException, "log push failed for 1 of 2"):
            sweep([failed_batch, other_batch])
        self.assertEqual(load_watermarks(watermark), {OTHER: 42})
        streams = [stream for _, payload in loki.requests for stream in payload]
        self.assertTrue(any(stream["values"][0][1] == early for stream in streams))
        self.assertGreaterEqual(sum(any("late" in entry[1] for entry in stream["values"])
                                    for stream in streams), 3)
        self.assertFalse(any("service" in stream["stream"] for stream in streams))

        loki.reject = False
        loki.requests.clear()
        sweep([failed_batch])
        self.assertEqual(load_watermarks(watermark), candidate)
        self.assertTrue(all(size < 1_000_000 for size, _ in loki.requests))
        received = [entry for _, payload in loki.requests for stream in payload
                    if stream["stream"] == failed_batch["labels"] for entry in stream["values"]]
        self.assertEqual(received, [[str(timestamp_ns + index), line, metadata]
                                    for index, line in enumerate(lines)])

        loki.requests.clear()
        sweep([])
        self.assertEqual(len(loki.requests), 1)
        _, streams = loki.requests[0]
        self.assertEqual(streams[0]["stream"], {"service": "fleet-logs"})
        self.assertEqual(streams[0]["values"][0][1], "Fleet log sweep complete")


if __name__ == "__main__":
    unittest.main()
