"""
Text extraction orchestrator - coordinates extraction from XML, HTML, and PDF files.

This module imports specialized extractors and provides high-level orchestration functions.
"""

import re
import time
import random
from pathlib import Path
from typing import Dict
import json
from datetime import datetime

# Import all common functions from common.py
from .common import (
    download_with_retry,
    download_bill_text,
    record_failed_bill,
    save_failed_bills_report,
    reset_error_tracking,
    rotate_session,
    get_congress_gov_headers,
    fetch_working_proxies,
)

# Import specialized extractors
from .xml_extractor import extract_text_from_xml
from .html_extractor import download_html_content, extract_text_from_html
from .pdf_extractor import (
    download_pdf_content,
    extract_text_from_pdf,
    extract_text_with_strikethroughs,
    debug_pdf_structure,
)


def create_safe_filename(
    url: str, version_note: str = "", file_extension: str = "xml"
) -> str:
    """
    Create a safe filename from URL and version note.

    Args:
        url: The URL to extract filename from
        version_note: Version note to include in filename
        file_extension: File extension to use (xml, html, pdf, etc.)

    Returns:
        Safe filename
    """
    # Extract filename from URL
    filename = url.split("/")[-1]
    if not filename or "." not in filename:
        filename = f"bill_content.{file_extension}"

    # Clean up version note for filename
    safe_version = re.sub(r"[^\w\s-]", "", version_note).strip()
    safe_version = re.sub(r"[-\s]+", "_", safe_version)

    if safe_version:
        name, ext = filename.rsplit(".", 1)
        filename = f"{name}_{safe_version}.{ext}"

    return filename


def download_congress_gov_content(url: str) -> str:
    """Download content from congress.gov with specialized anti-blocking techniques."""
    try:
        # Fetch working proxies for aggressive mode
        fetch_working_proxies()

        # For amendment URLs, try the /text endpoint first
        if "/amendment/" in url and not url.endswith("/text"):
            text_url = url + "/text"
            print(f"   🔄 Trying /text endpoint: {text_url}")

            # Try the /text endpoint first with aggressive mode
            response = download_with_retry(
                text_url, max_retries=5, delay=2.0, use_aggressive_mode=True
            )
            if response:
                return response.text

            print(f"   ⚠️ /text endpoint failed, trying original URL: {url}")

        # Try the enhanced retry function on original URL with aggressive mode
        response = download_with_retry(
            url, max_retries=5, delay=2.0, use_aggressive_mode=True
        )
        if response:
            return response.text

        # If that fails, try a different approach with session warming
        print(f"   🔄 Trying session warming approach for {url}")

        # Warm up the session by visiting the main page first
        session = rotate_session()
        warmup_headers = get_congress_gov_headers()

        try:
            # Visit main page to establish session
            session.get(
                "https://www.congress.gov/",
                headers=warmup_headers,
                timeout=30,
                verify=False,
            )
            time.sleep(random.uniform(2, 4))

            # For amendment URLs, try /text endpoint first
            target_url = url
            if "/amendment/" in url and not url.endswith("/text"):
                target_url = url + "/text"
                print(f"   🔄 Session warming: trying /text endpoint: {target_url}")

            # Now try the target URL
            response = session.get(
                target_url, headers=warmup_headers, timeout=45, verify=False
            )
            if response.status_code == 200:
                return response.text

            # If /text failed, try original URL
            if target_url != url:
                print(f"   🔄 Session warming: trying original URL: {url}")
                response = session.get(
                    url, headers=warmup_headers, timeout=45, verify=False
                )
                if response.status_code == 200:
                    return response.text
        except:
            pass

        # Final fallback: try with curl-like headers
        print(f"   🔄 Trying curl-like approach for {url}")
        curl_headers = {
            "User-Agent": "curl/7.68.0",
            "Accept": "*/*",
            "Connection": "keep-alive",
        }

        session = rotate_session()

        # For amendment URLs, try /text endpoint first
        target_url = url
        if "/amendment/" in url and not url.endswith("/text"):
            target_url = url + "/text"
            print(f"   🔄 Curl fallback: trying /text endpoint: {target_url}")

        response = session.get(
            target_url, headers=curl_headers, timeout=45, verify=False
        )
        if response.status_code == 200:
            return response.text

        # If /text failed, try original URL
        if target_url != url:
            print(f"   🔄 Curl fallback: trying original URL: {url}")
            response = session.get(url, headers=curl_headers, timeout=45, verify=False)
            if response.status_code == 200:
                return response.text

        return None

    except Exception as e:
        print(f"   ❌ Failed to download congress.gov content: {e}")
        return None


def extract_bill_text_from_metadata(
    metadata_file: Path, files_dir: Path, output_folder: Path = None
) -> bool:
    """
    Extract bill text for a single bill from its metadata.json file.

    Args:
        metadata_file: Path to metadata.json file
        files_dir: Path to files/ directory for this bill
        output_folder: Path to calling repo root for error reporting (optional)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load metadata
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Extract bill ID for error tracking
        bill_id = metadata.get("identifier", "unknown")
        if not bill_id or bill_id == "unknown":
            # Try to extract from file path as fallback
            bill_id = metadata_file.parent.name

        # Define media type preference order (best to worst)
        MEDIA_TYPE_PREFERENCE = [
            "text/xml",  # Best: Structured XML data
            "text/html",  # Good: HTML content
            "application/pdf",  # Acceptable: PDF files
            "text/plain",  # Basic: Plain text
        ]

        # Process only versions array (primary bill text)
        # Skip documents array (contains amendments/supporting materials that often fail to download)
        arrays_to_process = []

        # Add versions array (contains actual bill text)
        versions = metadata.get("versions", [])
        if versions:
            arrays_to_process.append(("versions", versions))

        if not arrays_to_process:
            # This is normal - not all bills have full text available
            return True  # Don't count as error

        success_count = 0

        for array_name, items in arrays_to_process:
            priority = "🟢 PRIMARY" if array_name == "versions" else "🟡 SUPPORTING"
            print(f"   📋 Processing {array_name} array... ({priority})")

            for item in items:
                item_note = item.get("note", "")
                links = item.get("links", [])

                if not links:
                    continue  # Skip items without links

                # Find best available link based on preference order
                best_link = None
                best_media_type = None

                for link in links:
                    media_type = link.get("media_type", "")
                    url = link.get("url")

                    if not url:
                        continue

                    # Check if this media type is better than current best
                    for preferred_type in MEDIA_TYPE_PREFERENCE:
                        if preferred_type in media_type.lower():
                            if best_link is None or MEDIA_TYPE_PREFERENCE.index(
                                preferred_type
                            ) < MEDIA_TYPE_PREFERENCE.index(best_media_type):
                                best_link = link
                                best_media_type = preferred_type
                            break

                if not best_link:
                    continue  # Skip if no suitable link found

                url = best_link.get("url")
                media_type = best_link.get("media_type", "")

                print(f"   📥 Downloading: {url} (type: {media_type})")

                # Download content based on media type
                content = None
                strikethrough_info = None

                if "xml" in media_type.lower():
                    content = download_bill_text(url)
                elif "html" in media_type.lower():
                    content = download_html_content(
                        url, download_with_retry, download_congress_gov_content
                    )
                elif "pdf" in media_type.lower():
                    # Try enhanced strikethrough detection first
                    strikethrough_result = extract_text_with_strikethroughs(
                        url, download_with_retry
                    )
                    if strikethrough_result and strikethrough_result.get("raw_text"):
                        content = strikethrough_result["raw_text"]
                        strikethrough_info = {
                            "has_strikethroughs": strikethrough_result.get(
                                "has_strikethroughs", False
                            ),
                            "strikethrough_count": strikethrough_result.get(
                                "strikethrough_count", 0
                            ),
                        }
                        if strikethrough_info["has_strikethroughs"]:
                            print(
                                f"   🔍 Detected {strikethrough_info['strikethrough_count']} strikethrough sections"
                            )
                    else:
                        # Fallback to regular PDF extraction
                        content = download_pdf_content(url, download_with_retry)
                else:
                    print(f"   ⚠️ Unsupported media type: {media_type}")
                    continue

                if not content:
                    print(f"   ❌ Failed to download: {url}")
                    record_failed_bill(
                        bill_id=bill_id,
                        error_type="download",
                        error_message=f"Failed to download content from {media_type}",
                        url=url,
                        metadata_file=str(metadata_file),
                        additional_info={
                            "media_type": media_type,
                            "item_note": item_note,
                        },
                        output_folder=output_folder,
                    )
                    continue

                print(f"   📄 Downloaded {len(content)} characters")

                # Extract text based on content type
                extracted_data = None
                if "xml" in media_type.lower():
                    extracted_data = extract_text_from_xml(content)
                elif "html" in media_type.lower():
                    extracted_data = extract_text_from_html(content)
                elif "pdf" in media_type.lower():
                    extracted_data = extract_text_from_pdf(content)
                else:
                    extracted_data = {
                        "raw_text": content,
                        "title": "",
                        "official_title": "",
                        "sections": [],
                    }

                if "error" in extracted_data:
                    print(f"   ❌ Failed to parse content: {extracted_data['error']}")
                    record_failed_bill(
                        bill_id=bill_id,
                        error_type="parsing",
                        error_message=extracted_data["error"],
                        url=url,
                        metadata_file=str(metadata_file),
                        additional_info={
                            "media_type": media_type,
                            "item_note": item_note,
                        },
                        output_folder=output_folder,
                    )
                    continue

                # Create filenames
                file_extension = (
                    "xml"
                    if "xml" in media_type.lower()
                    else "html" if "html" in media_type.lower() else "pdf"
                )
                filename = create_safe_filename(url, item_note, file_extension)
                # Handle both lowercase and uppercase extensions (e.g., .html vs .HTM)
                if filename.endswith(f".{file_extension}"):
                    text_filename = filename.replace(
                        f".{file_extension}", "_extracted.txt"
                    )
                elif filename.endswith(f".{file_extension.upper()}"):
                    text_filename = filename.replace(
                        f".{file_extension.upper()}", "_extracted.txt"
                    )
                else:
                    # Fallback: just append _extracted.txt
                    text_filename = filename.rsplit(".", 1)[0] + "_extracted.txt"

                # Create appropriate directory structure
                if array_name == "documents":
                    # Put documents in a separate subfolder
                    target_dir = files_dir / "documents"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    print(f"   📁 Created documents directory: {target_dir}")
                else:
                    # Put versions in the main files directory
                    target_dir = files_dir
                    target_dir.mkdir(parents=True, exist_ok=True)
                    print(f"   📁 Created directory: {target_dir}")

                # Save original content
                content_file = target_dir / filename
                print(f"   💾 Saving {file_extension.upper()} to: {content_file}")
                try:
                    with open(content_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"   ✅ {file_extension.upper()} saved successfully")
                except Exception as e:
                    print(f"   ❌ Error saving {file_extension.upper()}: {e}")
                    continue

                # Save extracted text
                text_file = target_dir / text_filename
                print(f"   💾 Saving extracted text to: {text_file}")
                try:
                    with open(text_file, "w", encoding="utf-8") as f:
                        f.write(f"Title: {extracted_data.get('title', 'N/A')}\n")
                        f.write(
                            f"Official Title: {extracted_data.get('official_title', 'N/A')}\n"
                        )
                        f.write(
                            f"Number of Sections: {len(extracted_data.get('sections', []))}\n"
                        )
                        f.write(f"Source: {array_name} - {item_note}\n")
                        f.write(f"Media Type: {media_type}\n")
                        if strikethrough_info and strikethrough_info.get(
                            "has_strikethroughs"
                        ):
                            f.write(
                                f"Strikethrough Detection: {strikethrough_info['strikethrough_count']} sections found\n"
                            )
                        f.write("\n" + "=" * 80 + "\n\n")

                        for i, section in enumerate(
                            extracted_data.get("sections", []), 1
                        ):
                            f.write(f"Section {i}:\n{section}\n\n")

                        f.write("\n" + "=" * 80 + "\n\n")
                        f.write("Raw Text:\n")
                        f.write(extracted_data.get("raw_text", ""))
                    print(f"   ✅ Text saved successfully")
                except Exception as e:
                    print(f"   ❌ Error saving text: {e}")
                    record_failed_bill(
                        bill_id=bill_id,
                        error_type="save",
                        error_message=f"Failed to save extracted text: {e}",
                        url=url,
                        metadata_file=str(metadata_file),
                        additional_info={
                            "media_type": media_type,
                            "item_note": item_note,
                            "text_filename": text_filename,
                        },
                        output_folder=output_folder,
                    )
                    continue

                success_count += 1
                print(f"   ✅ Extracted text for {array_name}: {item_note}")

        return success_count > 0

    except Exception as e:
        print(f"   ❌ Error processing {metadata_file}: {e}")
        return False


def process_bills_in_batch(
    processed_folder: Path,
    batch_size: int = 100,
    output_folder: Path = None,
    state: str = "unknown",
    incremental: bool = False,
) -> Dict[str, int]:
    """
    Process bills in batches for text extraction.

    Args:
        processed_folder: Path to the processed data folder
        batch_size: Number of bills to process in each batch
        output_folder: Path to save error reports (optional)
        state: State identifier for error reports (optional)

    Returns:
        Dictionary with processing statistics
    """
    # Reset error tracking for this run
    reset_error_tracking()

    # Find all metadata.json files
    metadata_files = list(processed_folder.rglob("metadata.json"))

    total_bills = len(metadata_files)
    processed_count = 0
    success_count = 0
    error_count = 0
    skipped_count = 0

    print(f"📊 Found {total_bills} bills to process for text extraction")

    if incremental:
        print("🔄 Incremental mode enabled - checking for already processed bills")

    # Process in batches
    for i in range(0, total_bills, batch_size):
        batch = metadata_files[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_bills + batch_size - 1) // batch_size

        print(f"\n🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} bills)")

        for metadata_file in batch:
            try:
                # Check if we should skip this bill in incremental mode
                if incremental and should_skip_bill_for_text_extraction(metadata_file):
                    skipped_count += 1
                    processed_count += 1
                    continue

                # Get the files directory for this bill
                files_dir = metadata_file.parent / "files"
                files_dir.mkdir(parents=True, exist_ok=True)

                # Extract text for this bill
                success = extract_bill_text_from_metadata(
                    metadata_file, files_dir, output_folder
                )

                if success:
                    success_count += 1
                    # Update processing timestamp
                    update_text_extraction_timestamp(metadata_file)
                else:
                    error_count += 1

                processed_count += 1

                # Progress indicator
                if processed_count % 10 == 0:
                    print(f"   Processed {processed_count}/{total_bills} bills...")

            except Exception as e:
                print(f"❌ Error processing {metadata_file}: {e}")
                error_count += 1
                processed_count += 1

        print(
            f"✅ Batch {batch_num} complete. Success: {success_count}, Errors: {error_count}, Skipped: {skipped_count}"
        )

    # Save error report if output folder is provided
    if output_folder:
        save_failed_bills_report(output_folder, state)

    return {
        "total_bills": total_bills,
        "processed": processed_count,
        "successful": success_count,
        "errors": error_count,
        "skipped": skipped_count,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python text_extraction.py <processed_folder_path>")
        sys.exit(1)

    processed_folder = Path(sys.argv[1])
    if not processed_folder.exists():
        print(f"❌ Folder does not exist: {processed_folder}")
        sys.exit(1)

    print("🚀 Starting bill text extraction...")
    stats = process_bills_in_batch(processed_folder)

    print(f"\n📊 Extraction Complete!")
    print(f"Total bills: {stats['total_bills']}")
    print(f"Processed: {stats['processed']}")
    print(f"Successful: {stats['successful']}")
    print(f"Errors: {stats['errors']}")
    if stats.get("skipped", 0) > 0:
        print(f"Skipped (already processed): {stats['skipped']}")


def should_skip_bill_for_text_extraction(metadata_file: Path) -> bool:
    """
    Check if a bill should be skipped for text extraction in incremental mode.

    Args:
        metadata_file: Path to the metadata.json file

    Returns:
        True if the bill should be skipped, False otherwise
    """
    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        bill_id = metadata.get("identifier", metadata_file.parent.name)

        # Check if text has already been extracted
        processing_info = metadata.get("_processing", {})
        text_extraction_timestamp = processing_info.get("text_extraction_latest_update")

        if not text_extraction_timestamp:
            # No text extraction timestamp - needs processing
            print(f"   🔍 {bill_id}: No extraction timestamp - processing")
            return False

        # Check if the bill has been updated since last text extraction
        logs_timestamp = processing_info.get("logs_latest_update")
        if logs_timestamp and logs_timestamp > text_extraction_timestamp:
            # Bill has been updated since last text extraction - needs processing
            print(f"   🔍 {bill_id}: Bill updated since last extraction - processing")
            return False

        # Check if any extracted text files exist
        files_dir = metadata_file.parent / "files"
        if not files_dir.exists():
            # No files directory - needs processing
            print(f"   🔍 {bill_id}: Files directory doesn't exist - processing")
            return False

        # Check if any _extracted.txt files exist
        extracted_files = list(files_dir.rglob("*_extracted.txt"))

        if not extracted_files:
            # No extracted text files - needs processing
            print(f"   🔍 {bill_id}: No extracted text files found - processing")
            return False

        # All checks passed - can skip this bill
        print(f"   ⏭️  {bill_id}: Already extracted - skipping")
        return True

    except Exception as e:
        print(f"   ⚠️ Error checking incremental status for {metadata_file}: {e}")
        # If we can't determine status, process it to be safe
        return False


def update_text_extraction_timestamp(metadata_file: Path) -> None:
    """
    Update the text extraction timestamp in the metadata file.

    Args:
        metadata_file: Path to the metadata.json file
    """
    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # Add or update the text extraction timestamp
        if "_processing" not in metadata:
            metadata["_processing"] = {}

        metadata["_processing"]["text_extraction_latest_update"] = (
            datetime.utcnow().isoformat() + "Z"
        )

        # Write back to file
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    except Exception as e:
        print(f"   ⚠️ Error updating text extraction timestamp for {metadata_file}: {e}")
