from __future__ import annotations

import argparse
import json
from pathlib import Path

from .parser import PDFStructuredExtractor, VisionModelClient, export_to_csv, export_to_sqlite


class JSONVisionClient(VisionModelClient):
    """Uses pre-extracted VLM responses from JSON for deterministic runs."""

    def __init__(self, json_path: str | Path) -> None:
        with Path(json_path).open("r", encoding="utf-8") as fp:
            self._responses: dict[str, str] = json.load(fp)

    def extract(self, image_bytes: bytes, page_number: int) -> str:
        _ = image_bytes
        return self._responses.get(str(page_number), "")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Parse non-OCR PDFs by rendering pages as images, reading them via a vision model, "
            "and exporting structured records to CSV or SQLite."
        )
    )
    parser.add_argument("--pdf", required=True, help="Input PDF path")
    parser.add_argument(
        "--vision-json",
        required=True,
        help="JSON file of VLM extracted text keyed by page number",
    )
    parser.add_argument("--csv", help="Output CSV path")
    parser.add_argument("--sqlite", help="Output SQLite DB path")

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    extractor = PDFStructuredExtractor(vision_client=JSONVisionClient(args.vision_json))
    parsed = extractor.extract(pdf_path)

    if args.csv:
        export_to_csv(parsed, args.csv)
    if args.sqlite:
        export_to_sqlite(parsed, args.sqlite)


if __name__ == "__main__":
    main()
