import xml.etree.ElementTree as ET
from typing import Dict


def extract_text_from_xml(xml_content: str) -> Dict[str, str]:
    """
    Extract clean text from XML bill content.

    Args:
        xml_content: XML content as string

    Returns:
        Dictionary with extracted text components
    """
    try:
        root = ET.fromstring(xml_content)

        # Extract title
        title = ""
        title_elem = root.find(".//title")
        if title_elem is not None:
            title = title_elem.text or ""

        # Extract official title
        official_title = ""
        official_title_elem = root.find(".//official-title")
        if official_title_elem is not None:
            official_title = official_title_elem.text or ""

        # Extract sections
        sections = []
        for section in root.findall(".//section"):
            section_text = ET.tostring(section, encoding="unicode", method="text")
            if section_text.strip():
                sections.append(section_text.strip())

        # Extract raw text (all text content)
        raw_text = ET.tostring(root, encoding="unicode", method="text")

        return {
            "title": title.strip(),
            "official_title": official_title.strip(),
            "sections": sections,
            "raw_text": raw_text.strip(),
        }

    except Exception as e:
        print(f"❌ Error parsing XML: {e}")
        return {"error": f"Failed to parse XML: {e}"}

