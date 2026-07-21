"""Shared HTTP helper: stdlib urllib with retry/backoff, no client libraries.

Used by the GitHub poller (GET) and the Grafana push (POST). Retry policy
mirrors the proven pattern in actions/pipeline-manager/check-sessions.py:
HTTP 429 honors Retry-After, 5xx and network errors back off exponentially,
4xx (other than 429) fails immediately — a bad request never gets better by
retrying. Exhausted retries raise RuntimeError with the URL and last error,
so callers decide whether that is fatal (a push) or recorded-and-skipped
(one repo in a poll).
"""

import json
import time
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_RETRIES = 3


def request_with_retry(
    url,
    *,
    data=None,
    headers=None,
    timeout=DEFAULT_TIMEOUT,
    max_retries=DEFAULT_MAX_RETRIES,
    sleep=time.sleep,
):
    """Return the response body (bytes) for a request, retrying transient failures.

    ``data`` (bytes) switches the request to POST. ``sleep`` is injectable so
    tests never wait.
    """
    last_error = None
    for attempt in range(max_retries):
        request = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 0) or 0)
                sleep(max(retry_after, 2 ** (attempt + 3)))
                continue
            if e.code >= 500:
                sleep(2 ** (attempt + 1))
                continue
            raise RuntimeError(f"{'POST' if data else 'GET'} {url}: HTTP {e.code}") from e
        except Exception as e:  # URLError, timeout, connection reset
            last_error = str(e)
            sleep(2 ** (attempt + 1))
    raise RuntimeError(f"{'POST' if data else 'GET'} {url}: giving up after {max_retries} attempts ({last_error})")


def request_json(url, *, headers=None, timeout=DEFAULT_TIMEOUT, max_retries=DEFAULT_MAX_RETRIES):
    """GET a URL and parse the JSON response body."""
    return json.loads(request_with_retry(url, headers=headers, timeout=timeout, max_retries=max_retries))
