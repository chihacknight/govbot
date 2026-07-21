from typing import Optional

# Phrases sites use when the actual bill text is behind client-side
# rendering (a JS-rendered shell, not real content). Not SD-specific --
# any state's bill-text site could ship the same "please enable
# JavaScript" boilerplate.
_JS_REQUIRED_PHRASES = (
    "enable javascript",
    "enable it to continue",
    "doesn't work properly without javascript",
    "does not work properly without javascript",
    "requires javascript",
)

# Below this many characters of extracted text, treat the page as
# suspect even without a matching phrase -- a real bill-text page (nav
# chrome and all) runs to thousands of characters, so anything this
# short is far more likely a loading shell than a short bill.
_PLACEHOLDER_TEXT_LENGTH_THRESHOLD = 200


def is_placeholder_html(html_content: str, extracted_text: str) -> bool:
    """
    Detect HTML that's a client-side-rendering loading shell rather than
    real bill content (e.g. a Vue/React SPA that serves the same static
    markup regardless of URL, with the actual text fetched via JS after
    load). Used to fall back to the next-preferred media type (e.g. PDF)
    instead of trusting near-empty "extracted" text.
    """
    lower_html = html_content.lower()
    if any(phrase in lower_html for phrase in _JS_REQUIRED_PHRASES):
        return True
    return len(extracted_text.strip()) < _PLACEHOLDER_TEXT_LENGTH_THRESHOLD


def download_html_content(url: str, download_with_retry_func, download_congress_gov_func) -> Optional[str]:
    """Download HTML content from URL with proper headers to avoid blocking."""
    try:
        # Use specialized function for congress.gov
        if "congress.gov" in url:
            return download_congress_gov_func(url)

        # Use standard retry for other sites
        response = download_with_retry_func(url, max_retries=3, delay=1.0)
        if not response:
            return None
        return response.text
    except Exception as e:
        print(f"   ❌ Failed to download HTML: {e}")
        return None


def extract_text_from_html(html_content: str) -> dict:
    """Extract text from HTML content."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = " ".join(chunk for chunk in chunks if chunk)

        return {
            "title": soup.title.string if soup.title else "",
            "official_title": "",
            "sections": [text],
            "raw_text": text,
            "is_placeholder": is_placeholder_html(html_content, text),
        }
    except ImportError:
        return {"error": "BeautifulSoup not available for HTML parsing"}
    except Exception as e:
        return {"error": f"Failed to parse HTML: {e}"}

