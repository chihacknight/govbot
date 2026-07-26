"""Shared HTTP helper: stdlib urllib with retry/backoff, no client libraries.

Used by the GitHub poller (GET) and the Grafana push (POST). Retry policy
mirrors the proven pattern in actions/pipeline-manager/check-sessions.py:
HTTP 429 honors Retry-After — as does a 403 that is really GitHub rate
limiting (Retry-After present or X-RateLimit-Remaining exhausted) — 5xx and
network errors back off exponentially, and any other 4xx fails immediately:
a bad request never gets better by retrying. One exception inside the
rate-limit branch: an exhausted quota with no Retry-After fails fast, since
its reset is typically up to an hour out and no in-sweep retry can succeed. Failures raise RequestFailed
(status carries the HTTP code for fail-fast 4xx), so callers decide whether
that is fatal (a push) or recorded-and-skipped (one repo in a poll). The
policy is locked by offline asserts in render-snapshots.sh (fake urlopen,
injected sleep).
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request


class _StripAuthOnCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but drop the Authorization header when the target host
    differs from the origin.

    GitHub's Actions log-download endpoint (``/actions/runs/{id}/logs``)
    302-redirects to Azure blob storage, with its credentials in the URL's SAS
    query string. A forwarded ``Authorization: Bearer <github-token>`` makes Azure
    answer 403 (it tries, and fails, to authenticate with the stray header instead
    of the SAS). Python < 3.13's urllib forwards the header across hosts, so we
    strip it ourselves — which also stops any token from ever leaking to a
    redirect target we didn't originate the request to.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            # Scheme and port, not just host: a same-host https→http redirect
            # would otherwise forward a bearer token in cleartext.
            def identity(url):
                parsed = urllib.parse.urlparse(url)
                # Default ports normalised, or a redirect that merely spells out
                # ":443" would read as cross-origin and drop the token on a hop
                # that never left the host.
                port = parsed.port or {"https": 443, "http": 80}.get(parsed.scheme)
                return (parsed.scheme, parsed.hostname, port)

            if identity(req.full_url) != identity(newurl):
                for key in [k for k in new.headers if k.lower() == "authorization"]:
                    del new.headers[key]
        return new


# Install process-wide so urllib.request.urlopen (which request_with_retry calls)
# strips Authorization on cross-host redirects. The offline suite patches urlopen
# directly and bypasses this opener, so it is unaffected; the live paths (log
# archive download, live-check) get the fix and the hardening.
urllib.request.install_opener(urllib.request.build_opener(_StripAuthOnCrossHostRedirect()))

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
    method=None,
    timeout=DEFAULT_TIMEOUT,
    max_retries=DEFAULT_MAX_RETRIES,
    sleep=time.sleep,
):
    """Return the response body (bytes) for a request, retrying transient failures.

    ``data`` (bytes) switches the request to POST; ``method`` overrides that,
    which is what the alert provisioning API needs — its update endpoints are
    PUT, and a PUT sent as a POST creates a duplicate instead of replacing.
    ``sleep`` is injectable so tests never wait.
    """
    method = method or ("POST" if data is not None else "GET")
    last_error = None
    for attempt in range(max_retries):
        request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
            if e.code == 429 or (e.code == 403 and _is_rate_limited(e.headers)):
                if not e.headers.get("Retry-After") and e.headers.get("X-RateLimit-Remaining") == "0":
                    # Quota exhausted with no Retry-After: the reset
                    # (X-RateLimit-Reset) is typically up to an hour away, so
                    # no in-sweep retry can succeed — fail fast and let the
                    # next scheduled sweep run after the window resets.
                    raise RequestFailed(
                        f"{method} {url}: HTTP {e.code} (rate limit exhausted)", status=e.code
                    ) from e
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
