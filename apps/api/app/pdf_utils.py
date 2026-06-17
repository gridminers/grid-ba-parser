from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass
class RenderedPage:
    page_number: int
    image_path: Path
    text: str
    width: int
    height: int


def render_pdf_pages(pdf_path: Path, output_dir: Path, dpi: int = 180) -> list[RenderedPage]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages: list[RenderedPage] = []
    document = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    try:
        for index, page in enumerate(document, start=1):
            image_path = output_dir / f"page-{index:03d}.png"
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(image_path)
            text = page.get_text("text") or ""
            pages.append(
                RenderedPage(
                    page_number=index,
                    image_path=image_path,
                    text=text,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
    finally:
        document.close()
    return pages
