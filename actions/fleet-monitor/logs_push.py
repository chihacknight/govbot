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
import os

from http_util import request_with_retry


def push_logs(payload: str, env=os.environ):
    """POST the Loki JSON payload; raises RuntimeError on missing env or failed push."""
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
        data=payload.encode(),
        headers={
            "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode(),
            "Content-Type": "application/json",
        },
    )
