import re
from collections.abc import Iterable

from .models import ExtractedField, ExtractedTable, WarningItem
from .normalization import fold_text, normalize_value, normalize_whitespace


KNOWN_LABELS = [
    "Projekttitel",
    "Projekt-ID",
    "beantr. Gruppe",
    "Projektverantwortlicher",
    "Geschaeftsjahr",
    "Ausfuehrungszeit",
    "Nachgenehmigungsantrag",
    "Genehmigungs-Nr.",
    "PSP-Element",
    "Materialkosten",
    "Fremdleistungen",
    "Eigenleistung",
    "Ingenieursleistungen",
    "Materialkostenzuschlag",
    "Investitionszuschlaege",
    "Gesamtkosten",
]


VALUE_PATTERNS = [
    re.compile(r"\bPROJ-\d+\b", re.I),
    re.compile(r"\b[A-Z0-9]{1,4}(?:[.\-][A-Z0-9]{2,}){2,}\b", re.I),
    re.compile(r"\b\d{2,4}/\d{2,4}\b"),
    re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"),
    re.compile(r"\b20\d{2}\b"),
    re.compile(r"[-+]?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})\s*(?:EUR|\u20ac)?", re.I),
    re.compile(r"[-+]?\d+(?:\.\d{2})\s*(?:EUR|\u20ac)?", re.I),
]


def _lines(text: str) -> list[str]:
    return [normalize_whitespace(line) for line in text.splitlines() if normalize_whitespace(line)]


def _best_value_fragment(fragment: str) -> str:
    cleaned = normalize_whitespace(fragment).strip(":-|")
    if not cleaned:
        return ""
    for pattern in VALUE_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return normalize_whitespace(match.group(0))
    return cleaned


def _field(label: str, value: str, page: int, source: str, evidence: str, confidence: float) -> ExtractedField:
    value_type, normalized = normalize_value(label, value)
    return ExtractedField(
        label=label,
        value_raw=value or None,
        value_normalized=normalized,
        type=value_type,
        page=page,
        confidence=confidence,
        evidence=evidence[:500],
        source=source,  # type: ignore[arg-type]
    )


def _dedupe(fields: Iterable[ExtractedField]) -> list[ExtractedField]:
    seen: set[tuple[str, str | None, int]] = set()
    result: list[ExtractedField] = []
    for field in fields:
        key = (fold_text(field.label), field.value_normalized or field.value_raw, field.page)
        if key in seen:
            continue
        seen.add(key)
        result.append(field)
    return result


def extract_key_values(text: str, page: int, source: str = "embedded_text") -> list[ExtractedField]:
    lines = _lines(text)
    fields: list[ExtractedField] = []
    folded_labels = [(label, fold_text(label)) for label in KNOWN_LABELS]

    for index, line in enumerate(lines):
        folded_line = fold_text(line)

        for label, folded_label in folded_labels:
            if folded_label not in folded_line:
                continue
            start = folded_line.find(folded_label) + len(folded_label)
            candidate = line[start:].strip(" :-|")
            if not candidate and index + 1 < len(lines):
                candidate = lines[index + 1]
            value = _best_value_fragment(candidate)
            if value and fold_text(value) != folded_label:
                fields.append(_field(label, value, page, source, line, 0.72))

        if ":" in line:
            label, value = line.split(":", 1)
            if 2 <= len(label) <= 80 and value.strip():
                fields.append(_field(label.strip(), _best_value_fragment(value), page, source, line, 0.58))

        wide_split = re.split(r"\s{3,}", line, maxsplit=1)
        if len(wide_split) == 2:
            label, value = wide_split
            if 2 <= len(label) <= 80 and re.search(r"\d|[A-Z]{2,}", value):
                fields.append(_field(label.strip(), _best_value_fragment(value), page, source, line, 0.52))

    return _dedupe(fields)


def extract_table_blocks(text: str, page: int, source: str = "embedded_text") -> list[ExtractedTable]:
    rows: list[dict[str, str]] = []
    for line in _lines(text):
        folded = fold_text(line)
        if not any(token in folded for token in ("kosten", "leistung", "zuschlag")):
            continue
        amount_match = re.search(
            r"[-+]?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|[-+]?\d+(?:\.\d{2})",
            line,
        )
        if not amount_match:
            continue
        label = normalize_whitespace(line[: amount_match.start()].strip(" .:-0123456789"))
        amount = amount_match.group(0)
        value_type, normalized = normalize_value(label or "amount", amount)
        rows.append(
            {
                "label": label or "amount",
                "value_raw": amount,
                "value_normalized": normalized or amount,
                "type": value_type,
                "evidence": line[:500],
            }
        )

    if not rows:
        return []
    return [
        ExtractedTable(
            title="Detected cost-like rows",
            page=page,
            rows=rows,
            confidence=0.58,
            source=source,  # type: ignore[arg-type]
        )
    ]


def validate_draft_fields(fields: list[ExtractedField]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for index, field in enumerate(fields):
        if not field.label.strip():
            errors.append(f"fields[{index}].label is empty")
        if field.page < 1:
            errors.append(f"fields[{index}].page must be >= 1")
        if field.value_raw is None and field.value_normalized is None:
            warnings.append(f"fields[{index}] has no value")
        if field.confidence < 0.4:
            warnings.append(f"fields[{index}] low confidence: {field.label}")
    return errors, warnings


def warning(code: str, message: str, page: int | None = None) -> WarningItem:
    return WarningItem(code=code, message=message, page=page)
