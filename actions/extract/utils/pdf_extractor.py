from typing import Optional


def _extract_pages_text(pdf_bytes: bytes) -> Optional[str]:
    """Try pdfplumber, then PyPDF2, then PyMuPDF (fitz), in order of preference."""
    import io

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text_parts = [p.extract_text() for p in pdf.pages]
            text = "\n\n".join(t for t in text_parts if t)
            if text:
                print(f"   ✅ Successfully extracted PDF text using pdfplumber")
                return text
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️ pdfplumber failed: {e}")

    try:
        import PyPDF2

        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text_parts = [p.extract_text() for p in reader.pages]
        text = "\n\n".join(t for t in text_parts if t)
        if text:
            print(f"   ✅ Successfully extracted PDF text using PyPDF2")
            return text
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️ PyPDF2 failed: {e}")

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        text_parts = [page.get_text() for page in doc]
        doc.close()
        text = "\n\n".join(t for t in text_parts if t)
        if text:
            print(f"   ✅ Successfully extracted PDF text using PyMuPDF")
            return text
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️ PyMuPDF failed: {e}")

    return None


def _has_visual_markup(pdf_bytes: bytes) -> bool:
    """
    Cheap, deterministic check for whether a PDF likely contains redline markup
    (strikethrough/underline showing deleted/added legislative text) -- the
    common convention for amendment bills.

    Rather than trying to infer strikethrough from font names, character
    spacing, or color (unreliable -- most bill-drafting software doesn't
    encode it that way, and the heuristic caught as much normal formatting
    as real strikethroughs), this looks for what a real strikethrough
    actually is in most legislative PDFs: a short horizontal vector line or
    rectangle drawn over a line of text. Checks pdfplumber's `lines`/`rects`
    for any object that's mostly horizontal (much wider than tall) and
    vertically overlaps a text character's line -- a hallmark of an
    intentionally-drawn strike mark rather than a table border or page
    decoration (which tend to span a full column width or be vertical).

    This is a signal for routing (does this document need full-fidelity
    handling, e.g. handing the raw PDF to a vision-capable model, instead of
    plain text extraction), not an attempt to reconstruct the struck text
    itself.
    """
    import io

    try:
        import pdfplumber
    except ImportError:
        return False

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                chars = page.chars
                if not chars:
                    continue

                candidates = list(page.lines) + list(page.rects)
                if not candidates:
                    continue

                for obj in candidates:
                    width = obj["x1"] - obj["x0"]
                    height = obj.get("y1", obj.get("bottom", 0)) - obj.get(
                        "y0", obj.get("top", 0)
                    )
                    height = abs(height)
                    if width < 3 or width < height * 3:
                        # Not a short, wide, mostly-horizontal mark.
                        continue

                    obj_top = min(obj.get("top", 0), obj.get("bottom", 0))
                    obj_bottom = max(obj.get("top", 0), obj.get("bottom", 0))

                    for char in chars:
                        if char["x0"] >= obj["x1"] or char["x1"] <= obj["x0"]:
                            continue  # No horizontal overlap
                        # Covers both strikethrough (mark through the middle
                        # of the character) and underline (mark at the
                        # bottom edge) -- both matter equally here, since
                        # either indicates redline markup (added/deleted
                        # text) rather than a table border or page rule,
                        # which wouldn't line up with a character's height
                        # at all.
                        pad = 2
                        if (char["top"] - pad) <= obj_bottom and obj_top <= (
                            char["bottom"] + pad
                        ):
                            return True
    except Exception as e:
        print(f"   ⚠️ Visual markup check failed: {e}")
        return False

    return False


def extract_pdf(url: str, download_with_retry_func) -> Optional[dict]:
    """
    Download and extract a PDF bill document in one pass.

    Returns a dict with:
      - raw_bytes: the genuine, unmodified PDF bytes as downloaded (for
        storage, and for handing off to a vision-capable model later)
      - text: plain extracted text (no section-splitting -- one clean read)
      - has_visual_markup: cheap geometry-based signal for whether this
        document likely contains redline (strikethrough/underline) markup
        that plain text extraction can't faithfully represent

    Returns None if the download or every extraction library fails.
    """
    response = download_with_retry_func(url, max_retries=3, delay=1.0)
    if not response:
        return None

    raw_bytes = response.content
    text = _extract_pages_text(raw_bytes)
    if not text:
        print(f"   ⚠️ No PDF parsing libraries available or all failed")
        return None

    return {
        "raw_bytes": raw_bytes,
        "text": text,
        "has_visual_markup": _has_visual_markup(raw_bytes),
    }
