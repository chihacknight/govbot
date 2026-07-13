"""
Common utilities for text extraction - simplified version.

This module provides basic download, retry, and error tracking functionality
without aggressive anti-blocking techniques.
"""

import requests
import time
import random
from pathlib import Path
from typing import Dict, Optional
import json
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create a single session with retry strategy
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Global error tracking
failed_bills_tracker = {
    "failed_downloads": [],
    "failed_parsing": [],
    "failed_saves": [],
    "total_failed": 0,
}


def get_realistic_headers() -> dict:
    """Get realistic browser headers."""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    ]

    return {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def record_failed_bill(
    bill_id: str,
    error_type: str,
    error_message: str,
    url: str = "",
    metadata_file: str = "",
    additional_info: Dict = None,
):
    """Record a failed bill for error tracking and reporting."""
    global failed_bills_tracker

    error_record = {
        "bill_id": bill_id,
        "error_type": error_type,
        "error_message": error_message,
        "url": url,
        "metadata_file": metadata_file,
        "timestamp": datetime.now().isoformat(),
        "additional_info": additional_info or {},
    }

    # Add to global tracker
    if error_type == "download":
        failed_bills_tracker["failed_downloads"].append(error_record)
    elif error_type == "parsing":
        failed_bills_tracker["failed_parsing"].append(error_record)
    elif error_type == "save":
        failed_bills_tracker["failed_saves"].append(error_record)

    failed_bills_tracker["total_failed"] += 1


def get_failed_bills_summary() -> Dict:
    """
    Return the current run's failed-bill tracker for the caller to print/report.

    Deliberately does not write anything to disk: a failed download of one
    document within an otherwise-fine bill isn't a bill-processing error (that's
    what .windycivi/errors/ is for -- missing_session, unknown_session, etc.),
    it's a per-run transient we want visible in the run's own summary output,
    not a permanent record persisted into the repo.
    """
    global failed_bills_tracker
    return failed_bills_tracker


def reset_error_tracking():
    """Reset the global error tracking for a new run."""
    global failed_bills_tracker
    failed_bills_tracker = {
        "failed_downloads": [],
        "failed_parsing": [],
        "failed_saves": [],
        "total_failed": 0,
    }


def download_with_retry(
    url: str,
    max_retries: int = 3,
    delay: float = 1.0,
    use_aggressive_mode: bool = False,
) -> Optional[requests.Response]:
    """Download with basic retry logic and exponential backoff."""

    for attempt in range(max_retries):
        try:
            # Add a small random delay to be respectful
            time.sleep(delay + random.uniform(0.5, 1.5))

            # Get headers
            headers = get_realistic_headers()

            # Make the request
            response = session.get(
                url,
                headers=headers,
                timeout=30,
                verify=False,
                allow_redirects=True,
            )

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                wait_time = delay * (2**attempt) + random.uniform(1, 3)
                print(f"   ⏳ Waiting {wait_time:.1f}s before retry...")
                time.sleep(wait_time)
            else:
                print(f"   ❌ All {max_retries} attempts failed for {url}")
                return None

    return None


def download_bill_text(url: str, delay: float = 1.0) -> Optional[str]:
    """
    Download bill text from a URL.

    Args:
        url: URL to download from
        delay: Delay between requests to be respectful

    Returns:
        Content as string, or None if failed
    """
    try:
        response = download_with_retry(url, max_retries=3, delay=delay)
        if not response:
            return None

        content_type = response.headers.get("content-type", "").lower()
        content = response.text

        # Check content type
        if (
            "xml" in content_type
            or content.strip().startswith("<?xml")
            or "<bill>" in content[:1000]
        ):
            return content
        else:
            print(f"⚠️ Unexpected content type: {content_type} for {url}")
            return None

    except Exception as e:
        print(f"❌ Error downloading {url}: {e}")
        return None


# Compatibility functions for congress.gov (kept for backward compatibility but simplified)
def rotate_session():
    """Return the session (kept for compatibility)."""
    return session


def get_congress_gov_headers() -> dict:
    """Get headers for congress.gov (same as realistic headers)."""
    return get_realistic_headers()


def fetch_working_proxies():
    """Placeholder function (no longer fetches proxies)."""
    pass
