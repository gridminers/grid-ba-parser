from pathlib import Path

from .config import Settings
from .extraction import extract_key_values, extract_table_blocks, warning
from .models import DocumentDraft, PageArtifact, WarningItem
from .ocr import OcrLine, run_ocr
from .pdf_utils import render_pdf_pages
from .storage import LocalStore
from .vlm import extract_page_with_vlm


def score_page(text: str, ocr_confidence: float | None) -> float:
    normalized = " ".join(text.split())
    score = 0.0
    if len(normalized) > 250:
        score += 0.35
    elif len(normalized) > 80:
        score += 0.2
    if any(token in normalized.lower() for token in ("psp", "projekt", "genehmigung", "kosten")):
        score += 0.25
    if any(char.isdigit() for char in normalized):
        score += 0.15
    if "\u20ac" in normalized or "EUR" in normalized:
        score += 0.1
    if ocr_confidence is not None:
        score += max(0.0, min(0.15, ocr_confidence * 0.15))
    return max(0.0, min(score, 1.0))


def _merge_texts(embedded_text: str, ocr_text: str) -> str:
    if len(ocr_text) > len(embedded_text) * 1.25:
        return f"{embedded_text}\n{ocr_text}".strip()
    return embedded_text or ocr_text


def _ocr_layout_payload(lines: list[OcrLine] | None) -> list[dict]:
    if not lines:
        return []
    return [
        {
            "text": line.text,
            "bbox": line.bbox,
            "confidence": line.confidence,
        }
        for line in lines
    ]


def _ocr_layout_context(lines: list[OcrLine] | None, max_lines: int = 90) -> str | None:
    if not lines:
        return None

    important_terms = (
        "projekt",
        "geschäftsjahr",
        "geschaeftsjahr",
        "ausführungszeit",
        "ausfuehrungszeit",
        "antragsgrund",
        "sparte",
        "asset",
        "psp",
        "leitung",
        "meter",
        "kosten",
        "leistung",
        "zuschlag",
        "gesamt",
        "zahlungsplan",
        "jahr",
        "eur",
        "€",
    )

    def score(line: OcrLine) -> tuple[int, int, int]:
        text = line.text.lower()
        term_score = sum(1 for term in important_terms if term in text)
        numeric_score = 1 if any(char.isdigit() for char in text) else 0
        return (-term_score, -numeric_score, line.bbox[1])

    prioritized = sorted(lines, key=score)[:max_lines]
    ordered = sorted(prioritized, key=lambda line: (line.bbox[1], line.bbox[0]))
    rows = []
    for line in ordered:
        text = " ".join(line.text.split())[:220]
        rows.append(f"bbox={line.bbox} text={text}")
    return "\n".join(rows)


def parse_document(
    *,
    document_id: str,
    store: LocalStore,
    settings: Settings,
    force_vlm_pages: set[int] | None = None,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> DocumentDraft:
    force_vlm_pages = force_vlm_pages or set()
    if vlm_provider or vlm_model:
        updates = {}
        if vlm_provider:
            updates["vlm_provider"] = vlm_provider
        effective_provider = vlm_provider or settings.vlm_provider
        if vlm_model:
            if effective_provider == "ollama":
                updates["ollama_model"] = vlm_model
            elif effective_provider == "local_vllm":
                updates["local_vllm_model"] = vlm_model
            elif effective_provider == "openai":
                updates["openai_vision_model"] = vlm_model
        settings = settings.model_copy(update=updates)
    record = store.get_document(document_id)
    record.status = "parsing"
    store.save_document(record)

    store.clear_pages(document_id)
    pages_dir = store.pages_dir(document_id)
    rendered_pages = render_pdf_pages(Path(record.source_path), pages_dir)
    all_fields = []
    all_tables = []
    all_warnings: list[WarningItem] = []
    artifacts: list[PageArtifact] = []
    raw_text_parts: list[str] = []

    for rendered in rendered_pages:
        page_number = rendered.page_number
        text_path = pages_dir / f"page-{page_number:03d}.txt"
        ocr_result = run_ocr(rendered.image_path)
        merged_text = _merge_texts(rendered.text, ocr_result.text)
        text_path.write_text(merged_text, encoding="utf-8")
        layout_path = pages_dir / f"page-{page_number:03d}.layout.json"
        layout_payload = _ocr_layout_payload(ocr_result.lines)
        if layout_payload:
            store.save_json(layout_path, layout_payload)
        layout_context = _ocr_layout_context(ocr_result.lines)
        quality_score = score_page(merged_text, ocr_result.confidence)
        route = "local"
        page_warnings: list[WarningItem] = []
        raw_text_parts.append(f"\n--- page {page_number} ---\n{merged_text}")

        use_vlm = page_number in force_vlm_pages or quality_score < settings.low_confidence_threshold
        if use_vlm and settings.enable_vlm and settings.vlm_available:
            try:
                vlm_draft, debug_payload = extract_page_with_vlm(
                    image_path=rendered.image_path,
                    page_number=page_number,
                    settings=settings,
                    ocr_layout_context=layout_context,
                )
                vlm_path = pages_dir / f"page-{page_number:03d}.vlm.json"
                store.save_json(vlm_path, debug_payload)
                all_fields.extend(vlm_draft.fields)
                all_tables.extend(vlm_draft.tables)
                all_warnings.extend(vlm_draft.warnings)
                route = settings.vlm_provider
            except Exception as exc:
                route = "local_vlm_failed"
                page_warnings.append(warning("vlm_failed", str(exc), page_number))
                all_fields.extend(extract_key_values(merged_text, page_number, source="heuristic"))
                all_tables.extend(extract_table_blocks(merged_text, page_number, source="heuristic"))
        else:
            if use_vlm and not settings.vlm_available:
                page_warnings.append(
                    warning("vlm_skipped", "Configured VLM provider is not available", page_number)
                )
                route = "local_low_confidence"
            all_fields.extend(extract_key_values(merged_text, page_number, source="embedded_text"))
            all_tables.extend(extract_table_blocks(merged_text, page_number, source="embedded_text"))

        if ocr_result.error:
            page_warnings.append(warning("ocr_unavailable", ocr_result.error, page_number))
        all_warnings.extend(page_warnings)
        artifacts.append(
            PageArtifact(
                page=page_number,
                image_path=str(rendered.image_path),
                image_url=store.artifact_url(rendered.image_path),
                text_path=str(text_path),
                vlm_response_path=str(pages_dir / f"page-{page_number:03d}.vlm.json")
                if (pages_dir / f"page-{page_number:03d}.vlm.json").exists()
                else None,
                route=route,
                quality_score=quality_score,
                ocr_confidence=ocr_result.confidence,
                warnings=page_warnings,
            )
        )

    draft = DocumentDraft(
        document_id=document_id,
        fields=all_fields,
        tables=all_tables,
        pages=artifacts,
        warnings=all_warnings,
        raw_text="\n".join(raw_text_parts).strip(),
    )
    store.save_draft(draft)
    record = store.get_document(document_id)
    record.page_count = len(rendered_pages)
    record.status = "draft"
    store.save_document(record)
    return draft
