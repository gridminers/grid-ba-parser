from dataclasses import dataclass
from pathlib import Path


@dataclass
class OcrLine:
    text: str
    bbox: list[int]
    confidence: float | None = None


@dataclass
class OcrResult:
    text: str = ""
    confidence: float | None = None
    error: str | None = None
    lines: list[OcrLine] | None = None


def _bbox_union(boxes: list[tuple[int, int, int, int]]) -> list[int]:
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    return [left, top, right, bottom]


def _ocr_lines_from_data(data: dict[str, list]) -> list[OcrLine]:
    grouped: dict[tuple[int, int, int], dict[str, list]] = {}
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text or "").strip()
        if not text:
            continue
        try:
            confidence = float(data.get("conf", [])[index])
        except (IndexError, TypeError, ValueError):
            confidence = -1.0
        if confidence < 0:
            continue

        try:
            left = int(data.get("left", [])[index])
            top = int(data.get("top", [])[index])
            width = int(data.get("width", [])[index])
            height = int(data.get("height", [])[index])
        except (IndexError, TypeError, ValueError):
            continue

        try:
            key = (
                int(data.get("block_num", [0])[index]),
                int(data.get("par_num", [0])[index]),
                int(data.get("line_num", [0])[index]),
            )
        except (IndexError, TypeError, ValueError):
            key = (0, 0, index)
        item = grouped.setdefault(key, {"words": [], "boxes": [], "confidences": []})
        item["words"].append(text)
        item["boxes"].append((left, top, left + width, top + height))
        item["confidences"].append(confidence)

    lines = []
    for item in grouped.values():
        confidences = item["confidences"]
        confidence = (sum(confidences) / len(confidences) / 100) if confidences else None
        lines.append(
            OcrLine(
                text=" ".join(item["words"]),
                bbox=_bbox_union(item["boxes"]),
                confidence=confidence,
            )
        )
    return sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))


def run_ocr(image_path: Path, lang: str = "deu+eng") -> OcrResult:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:  # pragma: no cover - depends on optional local install
        return OcrResult(error=f"OCR dependency unavailable: {exc}")

    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang=lang)
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
        confidences = []
        for raw_confidence in data.get("conf", []):
            try:
                value = float(raw_confidence)
            except (TypeError, ValueError):
                continue
            if value >= 0:
                confidences.append(value)
        confidence = (sum(confidences) / len(confidences) / 100) if confidences else None
        return OcrResult(text=text, confidence=confidence, lines=_ocr_lines_from_data(data))
    except Exception as exc:  # pragma: no cover - depends on system binary
        return OcrResult(error=f"OCR failed: {exc}")
