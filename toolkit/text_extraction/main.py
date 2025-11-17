import click
from pathlib import Path
import sys

# Add the current directory to the path
sys.path.append(str(Path(__file__).parent))

from utils.text_extraction import process_bills_in_batch


@click.command()
@click.option(
    "--state",
    required=True,
    help="Jurisdiction code to process (e.g., usa, wy, tx).",
)
@click.option(
    "--data-folder",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Path to the repo root containing bill data (with country:us/ structure).",
)
@click.option(
    "--output-folder",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    required=False,
    help="Path to the calling repo's root folder for error reports (optional).",
)
@click.option(
    "--incremental",
    is_flag=True,
    help="Enable incremental processing - only extract text for bills that haven't been processed or have been updated.",
)
def main(
    state: str, data_folder: Path, output_folder: Path = None, incremental: bool = False
):
    """
    Extract text from PDFs and XMLs in processed bill data.

    This tool processes existing bill data and extracts text from PDF and XML files
    found in the bill folders, creating _extracted.txt files for each document.
    """
    print(f"🚀 Starting text extraction for {state}")
    print(f"📁 Processing data in: {data_folder}")

    # Verify the data folder exists and has the expected structure
    if not data_folder.exists():
        print(f"❌ Data folder does not exist: {data_folder}")
        return 1

    # Check if we have any bill data
    bill_folders = list(data_folder.glob("country:us/state:*/sessions/*/bills/*"))
    if not bill_folders:
        print(f"❌ No bill folders found in: {data_folder}")
        print("Expected structure: country:us/state:*/sessions/*/bills/*")
        return 1

    print(f"📄 Found {len(bill_folders)} bill folders to process")

    # Run text extraction
    try:
        stats = process_bills_in_batch(
            data_folder,
            output_folder=output_folder,
            state=state,
            incremental=incremental,
        )

        print(f"\n📊 Text Extraction Complete!")
        print(f"Total bills: {stats['total_bills']}")
        print(f"Processed: {stats['processed']}")
        print(f"Successful: {stats['successful']}")
        print(f"Errors: {stats['errors']}")
        if stats.get("skipped", 0) > 0:
            print(f"Skipped (already processed): {stats['skipped']}")

        if stats["errors"] > 0:
            print(f"⚠️ {stats['errors']} bills had errors during processing")
            return 1
        else:
            print("✅ All bills processed successfully!")
            return 0

    except Exception as e:
        print(f"❌ Error during text extraction: {e}")
        return 1


if __name__ == "__main__":
    main(auto_envvar_prefix="TEXT_EXTRACT")
