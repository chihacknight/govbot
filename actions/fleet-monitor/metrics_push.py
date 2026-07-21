"""Push an encoded metric payload to the Grafana Cloud Influx write endpoint.

Credentials come from the environment — the module never persists them:

    GRAFANA_PUSH_URL   e.g. https://influx-prod-XX.grafana.net/api/v1/push/influx/write
    GRAFANA_PUSH_USER  the stack's metrics instance ID (Basic auth username)
    GRAFANA_PUSH_KEY   a Grafana Cloud access-policy token with metrics:write
"""

import base64
import os

from http_util import request_with_retry


def push_metrics(payload: str, env=os.environ):
    """POST the line-protocol payload; raises RuntimeError on missing env or failed push."""
    missing = [
        name
        for name in ("GRAFANA_PUSH_URL", "GRAFANA_PUSH_USER", "GRAFANA_PUSH_KEY")
        if not env.get(name)
    ]
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
    credentials = f"{env['GRAFANA_PUSH_USER']}:{env['GRAFANA_PUSH_KEY']}"
    request_with_retry(
        env["GRAFANA_PUSH_URL"],
        data=payload.encode(),
        headers={
            "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode(),
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
