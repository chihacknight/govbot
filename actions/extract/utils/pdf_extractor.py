import re
from typing import Optional


def download_pdf_content(url: str, download_with_retry_func) -> Optional[str]:
    """Download PDF content from URL and convert to text."""
    try:
        response = download_with_retry_func(url, max_retries=3, delay=1.0)
        if not response:
            return None

        # Try multiple PDF parsing libraries in order of preference
        pdf_content = None

        # Try pdfplumber first (best for complex layouts)
        try:
            import pdfplumber
            import io

            pdf_file = io.BytesIO(response.content)
            with pdfplumber.open(pdf_file) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                pdf_content = "\n\n".join(text_parts)
                if pdf_content:
                    print(f"   ✅ Successfully extracted PDF text using pdfplumber")
                    return pdf_content
        except ImportError:
            pass
        except Exception as e:
            print(f"   ⚠️ pdfplumber failed: {e}")

        # Try PyPDF2 as fallback
        try:
            import PyPDF2
            import io

            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text_parts = []
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            pdf_content = "\n\n".join(text_parts)
            if pdf_content:
                print(f"   ✅ Successfully extracted PDF text using PyPDF2")
                return pdf_content
        except ImportError:
            pass
        except Exception as e:
            print(f"   ⚠️ PyPDF2 failed: {e}")

        # Try pymupdf (fitz) as another fallback
        try:
            import fitz  # PyMuPDF
            import io

            pdf_file = io.BytesIO(response.content)
            doc = fitz.open(stream=pdf_file, filetype="pdf")
            text_parts = []
            for page in doc:
                page_text = page.get_text()
                if page_text:
                    text_parts.append(page_text)
            doc.close()
            pdf_content = "\n\n".join(text_parts)
            if pdf_content:
                print(f"   ✅ Successfully extracted PDF text using PyMuPDF")
                return pdf_content
        except ImportError:
            pass
        except Exception as e:
            print(f"   ⚠️ PyMuPDF failed: {e}")

        # If all libraries fail, return a placeholder
        print(f"   ⚠️ No PDF parsing libraries available")
        return f"[PDF content from {url} - requires PDF parsing library (pdfplumber, PyPDF2, or PyMuPDF)]"

    except Exception as e:
        print(f"   ❌ Failed to download PDF: {e}")
        return None


def extract_text_from_pdf(pdf_content: str) -> dict:
    """Extract text from PDF content."""
    # The pdf_content is already extracted text from the PDF
    # Clean up the text and structure it
    lines = pdf_content.split("\n")
    cleaned_lines = [line.strip() for line in lines if line.strip()]

    # Try to identify title and sections
    title = ""
    sections = []
    current_section = []

    for line in cleaned_lines:
        # Look for title patterns (usually at the top, all caps, or contains "AN ACT")
        if not title and (
            "AN ACT" in line.upper() or "BILL" in line.upper() or len(line) > 50
        ):
            title = line
        # Look for section headers (numbers, "SECTION", etc.)
        elif re.match(r"^(Section|§|\d+\.)", line, re.IGNORECASE):
            if current_section:
                sections.append("\n".join(current_section))
                current_section = []
            current_section.append(line)
        else:
            current_section.append(line)

    # Add the last section
    if current_section:
        sections.append("\n".join(current_section))

    # If no sections found, treat the whole content as one section
    if not sections:
        sections = [pdf_content]

    return {
        "title": title or "PDF Document",
        "official_title": title or "",
        "sections": sections,
        "raw_text": pdf_content,
    }


def extract_text_with_strikethroughs(url: str, download_with_retry_func) -> dict:
    """
    Extract PDF text including strikethrough content using visual analysis.

    This function attempts to detect strikethrough text by analyzing
    the visual layout and character positioning in the PDF.
    """
    try:
        response = download_with_retry_func(url, max_retries=3, delay=1.0)
        if not response:
            return None

        # Try pdfplumber with enhanced strikethrough detection
        try:
            import pdfplumber
            import io

            pdf_file = io.BytesIO(response.content)
            with pdfplumber.open(pdf_file) as pdf:
                text_parts = []
                strikethrough_parts = []

                for page in pdf.pages:
                    # Extract regular text
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)

                    # Try to detect strikethrough text using character analysis
                    chars = page.chars
                    if chars:
                        strikethrough_text = detect_strikethrough_chars(chars)
                        if strikethrough_text:
                            strikethrough_parts.append(
                                f"[DELETED: {strikethrough_text}]"
                            )

                # Combine regular and strikethrough text
                full_text = "\n\n".join(text_parts)
                if strikethrough_parts:
                    full_text += "\n\n" + "\n".join(strikethrough_parts)

                if full_text:
                    print(
                        f"   ✅ Successfully extracted PDF text with strikethrough detection using pdfplumber"
                    )
                    return {
                        "raw_text": full_text,
                        "has_strikethroughs": len(strikethrough_parts) > 0,
                        "strikethrough_count": len(strikethrough_parts),
                    }

        except ImportError:
            pass
        except Exception as e:
            print(f"   ⚠️ pdfplumber strikethrough detection failed: {e}")

        # Fallback to regular extraction
        return None

    except Exception as e:
        print(f"   ❌ Failed to download PDF for strikethrough analysis: {e}")
        return None


def detect_strikethrough_chars(chars: list) -> str:
    """
    Detect strikethrough text by analyzing character positioning and formatting.

    Args:
        chars: List of character objects from pdfplumber

    Returns:
        String containing detected strikethrough text
    """
    strikethrough_text = []

    # Group characters by line
    lines = {}
    for char in chars:
        y_pos = round(char["top"], 2)  # Round to handle floating point precision
        if y_pos not in lines:
            lines[y_pos] = []
        lines[y_pos].append(char)

    # Analyze each line for strikethrough patterns
    for y_pos, line_chars in lines.items():
        # Sort characters by x position
        line_chars.sort(key=lambda x: x["x0"])

        # Look for patterns that might indicate strikethrough
        for i, char in enumerate(line_chars):
            # Check if character has strikethrough-like properties
            if is_likely_strikethrough(char, line_chars, i):
                strikethrough_text.append(char["text"])

    return "".join(strikethrough_text)


def is_likely_strikethrough(char: dict, line_chars: list, index: int) -> bool:
    """
    Determine if a character is likely part of strikethrough text.

    This is a heuristic approach that looks for visual indicators
    of strikethrough text in PDF character data.
    """
    # Check for strikethrough font properties
    font_name = char.get("fontname", "").lower()
    if any(
        strike_indicator in font_name
        for strike_indicator in ["strike", "delete", "removed"]
    ):
        return True

    # Check for unusual character spacing or positioning
    if index > 0 and index < len(line_chars) - 1:
        prev_char = line_chars[index - 1]
        next_char = line_chars[index + 1]

        # Look for gaps in text that might indicate strikethrough
        gap_before = char["x0"] - prev_char["x1"]
        gap_after = next_char["x0"] - char["x1"]

        if gap_before > 2 or gap_after > 2:  # Unusual spacing
            return True

    # Check for color differences (strikethrough text might be grayed out)
    if "non_stroking_color" in char:
        color = char["non_stroking_color"]
        if isinstance(color, list) and len(color) >= 3:
            # Check if text is grayed out (common for strikethrough)
            r, g, b = color[:3]
            if r == g == b and r < 0.8:  # Gray text
                return True

    return False


def debug_pdf_structure(url: str, download_with_retry_func) -> dict:
    """
    Debug function to analyze PDF structure and identify potential strikethrough text.

    This function provides detailed information about the PDF's character layout,
    fonts, colors, and other properties that might indicate strikethrough text.
    """
    try:
        response = download_with_retry_func(url, max_retries=3, delay=1.0)
        if not response:
            return {"error": "Failed to download PDF"}

        import pdfplumber
        import io

        pdf_file = io.BytesIO(response.content)
        with pdfplumber.open(pdf_file) as pdf:
            debug_info = {
                "pages": len(pdf.pages),
                "fonts": set(),
                "colors": set(),
                "character_count": 0,
                "potential_strikethroughs": [],
            }

            for page_num, page in enumerate(pdf.pages):
                chars = page.chars
                debug_info["character_count"] += len(chars)

                for char in chars:
                    # Collect font information
                    font_name = char.get("fontname", "")
                    debug_info["fonts"].add(font_name)

                    # Collect color information
                    if "non_stroking_color" in char:
                        color = char["non_stroking_color"]
                        debug_info["colors"].add(str(color))

                    # Check for potential strikethrough indicators
                    if is_likely_strikethrough(char, chars, chars.index(char)):
                        debug_info["potential_strikethroughs"].append(
                            {
                                "page": page_num + 1,
                                "text": char["text"],
                                "font": char.get("fontname", ""),
                                "color": char.get("non_stroking_color", ""),
                                "position": (char["x0"], char["top"]),
                            }
                        )

            return debug_info

    except Exception as e:
        return {"error": str(e)}

