import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation


def fold_text(value: str) -> str:
    value = value.replace("\u00df", "ss")
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_value.lower()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_german_decimal(value: str) -> Decimal | None:
    cleaned = normalize_whitespace(value)
    cleaned = cleaned.replace("EUR", "").replace("eur", "").replace("Euro", "")
    cleaned = cleaned.replace("\u20ac", "").replace(" ", "")
    cleaned = re.sub(r"[^0-9,.\-]", "", cleaned)
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalize_date(value: str) -> str | None:
    text = normalize_whitespace(value)
    patterns = [
        ("%d.%m.%Y", r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"),
        ("%d/%m/%Y", r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
        ("%d.%m.%y", r"\b\d{1,2}\.\d{1,2}\.\d{2}\b"),
        ("%d/%m/%y", r"\b\d{1,2}/\d{1,2}/\d{2}\b"),
        ("%Y-%m-%d", r"\b\d{4}-\d{2}-\d{2}\b"),
    ]
    for date_format, regex in patterns:
        match = re.search(regex, text)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(0), date_format).date().isoformat()
        except ValueError:
            continue
    return None


def classify_value(label: str, value: str | None) -> str:
    label_folded = fold_text(label)
    raw = value or ""
    if "psp" in label_folded or "projekt-id" in label_folded or "genehmigungs" in label_folded:
        return "identifier"
    if "kosten" in label_folded or "\u20ac" in raw or re.search(r"\d+[,.]\d{2}\s*(eur|\u20ac)?", raw, re.I):
        return "currency"
    if "datum" in label_folded or "zeit" in label_folded or normalize_date(raw):
        return "date"
    if re.fullmatch(r"\d{4}", normalize_whitespace(raw)):
        return "year"
    if raw.lower() in {"ja", "nein", "true", "false", "x"}:
        return "boolean"
    if parse_german_decimal(raw) is not None and re.search(r"\d", raw):
        return "number"
    return "text"


def normalize_value(label: str, value: str | None) -> tuple[str, str | None]:
    value_type = classify_value(label, value)
    raw = normalize_whitespace(value or "")
    if value_type == "currency":
        amount = parse_german_decimal(raw)
        return value_type, f"{amount:.2f}" if amount is not None else raw
    if value_type == "date":
        return value_type, normalize_date(raw) or raw
    if value_type == "boolean":
        lowered = raw.lower()
        if lowered in {"ja", "true", "x"}:
            return value_type, "true"
        if lowered in {"nein", "false"}:
            return value_type, "false"
    return value_type, raw or None
