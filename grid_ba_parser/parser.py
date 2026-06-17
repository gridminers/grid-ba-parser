from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence


class VisionModelClient(Protocol):
    """Vision model contract: image bytes in, extracted text out."""

    def extract(self, image_bytes: bytes, page_number: int) -> str:
        ...


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    fields: dict[str, str]


class RuleBasedFormatter:
    """Converts loosely formatted model text into key-value pairs."""

    _DELIMITERS = (":", "=", "-")

    def parse(self, raw_text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in raw_text.splitlines():
            cleaned = line.strip()
            if not cleaned:
                continue

            for delimiter in self._DELIMITERS:
                if delimiter not in cleaned:
                    continue
                key, value = cleaned.split(delimiter, 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    result[key] = value
                break
        return result


def pdf_to_images(pdf_path: Path) -> list[bytes]:
    """Render each PDF page to PNG bytes for VLM processing."""

    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised only if dependency missing
        raise RuntimeError(
            "PyMuPDF (fitz) is required to render PDF pages as images. "
            "Install it with: pip install pymupdf"
        ) from exc

    images: list[bytes] = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            images.append(pix.tobytes("png"))
    return images


class PDFStructuredExtractor:
    def __init__(
        self,
        vision_client: VisionModelClient,
        formatter: RuleBasedFormatter | None = None,
        image_loader: Callable[[Path], Sequence[bytes]] = pdf_to_images,
    ) -> None:
        self._vision_client = vision_client
        self._formatter = formatter or RuleBasedFormatter()
        self._image_loader = image_loader

    def extract(self, pdf_path: str | Path) -> list[ParsedPage]:
        path = Path(pdf_path)
        pages = self._image_loader(path)
        parsed_pages: list[ParsedPage] = []

        for index, image_bytes in enumerate(pages, start=1):
            raw_text = self._vision_client.extract(image_bytes=image_bytes, page_number=index)
            fields = self._formatter.parse(raw_text)
            parsed_pages.append(ParsedPage(page_number=index, fields=fields))

        return parsed_pages


def export_to_csv(parsed_pages: Sequence[ParsedPage], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["page_number", "field", "value"])
        for page in parsed_pages:
            for field, value in page.fields.items():
                writer.writerow([page.page_number, field, value])


def export_to_sqlite(
    parsed_pages: Sequence[ParsedPage],
    database_path: str | Path,
    table_name: str = "parsed_records",
) -> None:
    connection = sqlite3.connect(str(database_path))
    try:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_number INTEGER NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL
            )
            """
        )

        cursor.execute(f"DELETE FROM {table_name}")
        cursor.executemany(
            f"INSERT INTO {table_name} (page_number, field, value) VALUES (?, ?, ?)",
            [
                (page.page_number, field, value)
                for page in parsed_pages
                for field, value in page.fields.items()
            ],
        )
        connection.commit()
    finally:
        connection.close()
