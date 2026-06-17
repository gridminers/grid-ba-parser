from dataclasses import dataclass
from pathlib import Path


@dataclass
class OcrResult:
    text: str = ""
    confidence: float | None = None
    error: str | None = None


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
        return OcrResult(text=text, confidence=confidence)
    except Exception as exc:  # pragma: no cover - depends on system binary
        return OcrResult(error=f"OCR failed: {exc}")
