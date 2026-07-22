"""Shared HTTP helper: stdlib urllib with retry/backoff, no client libraries.

Used by the GitHub poller (GET) and the Grafana push (POST). Retry policy
mirrors the proven pattern in actions/pipeline-manager/check-sessions.py:
HTTP 429 honors Retry-After — as does a 403 that is really GitHub rate
limiting (Retry-After present or X-RateLimit-Remaining exhausted) — 5xx and
network errors back off exponentially, and any other 4xx fails immediately:
a bad request never gets better by retrying. Failures raise RequestFailed
(status carries the HTTP code for fail-fast 4xx), so callers decide whether
that is fatal (a push) or recorded-and-skipped (one repo in a poll). The
policy is locked by offline asserts in render-snapshots.sh (fake urlopen,
injected sleep).
"""

import json
import time
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_RETRIES = 3


class RequestFailed(RuntimeError):
    """A request that will not be retried; ``status`` is the HTTP code when the
    failure was an HTTP error (None for gave-up-after-retries)."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _retry_after_seconds(response_headers):
    """Parse Retry-After as integer seconds; the RFC also allows an HTTP-date
    form, which falls back to 0 (the exponential default takes over)."""
    try:
        return int(response_headers.get("Retry-After") or 0)
    except ValueError:
        return 0


def _is_rate_limited(response_headers):
    """GitHub signals primary/secondary rate limiting as 403 (not 429), with a
    Retry-After header or an exhausted X-RateLimit-Remaining."""
    return bool(response_headers.get("Retry-After")) or (
        response_headers.get("X-RateLimit-Remaining") == "0"
    )


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
    method = "POST" if data is not None else "GET"
    last_error = None
    for attempt in range(max_retries):
        request = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
            if e.code == 429 or (e.code == 403 and _is_rate_limited(e.headers)):
                delay = max(_retry_after_seconds(e.headers), 2 ** (attempt + 3))
            elif e.code >= 500:
                delay = 2 ** (attempt + 1)
            else:
                raise RequestFailed(f"{method} {url}: HTTP {e.code}", status=e.code) from e
        except Exception as e:  # URLError, timeout, connection reset
            last_error = str(e)
            delay = 2 ** (attempt + 1)
        if attempt < max_retries - 1:  # no point sleeping before giving up
            sleep(delay)
    raise RequestFailed(f"{method} {url}: giving up after {max_retries} attempts ({last_error})")


def request_json(url, *, headers=None, timeout=DEFAULT_TIMEOUT, max_retries=DEFAULT_MAX_RETRIES):
    """GET a URL and parse the JSON response body."""
    return json.loads(request_with_retry(url, headers=headers, timeout=timeout, max_retries=max_retries))
