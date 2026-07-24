"""Push an encoded Loki payload to the Grafana Cloud Loki write endpoint.

Mirrors metrics_push: credentials come from the environment and are never
persisted, and the wire call reuses the shared http_util retry/backoff helper.
Only the endpoint, media type, and env-var names differ from the metrics push —
logs go to Loki as JSON, metrics to Influx as line protocol.

    GRAFANA_LOGS_URL   e.g. https://logs-prod-XX.grafana.net/loki/api/v1/push
    GRAFANA_LOGS_USER  the stack's logs instance ID (Basic auth username)
    GRAFANA_LOGS_KEY   a Grafana Cloud access-policy token with logs:write
"""

import base64
import gzip
import os

from http_util import request_with_retry

# Log payloads dwarf the metrics one: a single verbose failed run ships its full
# log — megabytes (a real Florida sweep measured ~9 MB). Two consequences the
# metrics push never faces, both handled here:
#   - gzip the body (log text compresses ~10x) so the upload is small and fast;
#     Loki accepts a gzipped push via Content-Encoding. Without it a multi-MB POST
#     blows the default socket write timeout.
#   - a generous timeout for the largest bodies over a slow uplink.
LOGS_PUSH_TIMEOUT = 120


def push_logs(payload: str, env=os.environ):
    """POST the Loki JSON payload (gzip-compressed); raises RuntimeError on missing
    env or failed push."""
    missing = [
        name
        for name in ("GRAFANA_LOGS_URL", "GRAFANA_LOGS_USER", "GRAFANA_LOGS_KEY")
        if not env.get(name)
    ]
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
    credentials = f"{env['GRAFANA_LOGS_USER']}:{env['GRAFANA_LOGS_KEY']}"
    request_with_retry(
        env["GRAFANA_LOGS_URL"],
        data=gzip.compress(payload.encode()),
        timeout=LOGS_PUSH_TIMEOUT,
        headers={
            "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode(),
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
        },
    )
