from typing import Optional


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
        }
    except ImportError:
        return {"error": "BeautifulSoup not available for HTML parsing"}
    except Exception as e:
        return {"error": f"Failed to parse HTML: {e}"}

