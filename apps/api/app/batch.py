from pathlib import Path

from .config import Settings
from .models import (
    DocumentDraft,
    DocumentRecord,
    MockDbExportPayload,
    MockDbExportResponse,
    MockDbField,
)
from .pipeline import parse_document
from .storage import LocalStore


def discover_pdfs(folder_path: Path, recursive: bool = False) -> list[Path]:
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder_path}")
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in folder_path.glob(pattern) if path.is_file())


def register_folder_pdfs(
    *,
    store: LocalStore,
    folder_path: Path,
    recursive: bool = False,
) -> list[DocumentRecord]:
    return [store.create_document_from_path(path) for path in discover_pdfs(folder_path, recursive)]


def mock_db_payload(record: DocumentRecord, draft: DocumentDraft) -> MockDbExportPayload:
    return MockDbExportPayload(
        document_id=record.id,
        filename=record.filename,
        sha256=record.sha256,
        fields=[
            MockDbField(
                label=field.label,
                sanitized_value=field.value_normalized or field.value_raw,
                value_normalized=field.value_normalized,
                value_raw=field.value_raw,
                type=field.type,
                page=field.page,
                confidence=field.confidence,
                source=field.source,
            )
            for field in draft.fields
            if field.label and (field.value_normalized is not None or field.value_raw is not None)
        ],
    )


def export_mock_db_payload(
    *,
    store: LocalStore,
    document_id: str,
) -> MockDbExportResponse:
    record = store.get_document(document_id)
    draft = store.get_draft(document_id)
    payload = mock_db_payload(record, draft)
    if not payload.fields:
        return MockDbExportResponse(
            status="skipped",
            message="No label/value fields available to export",
            document_id=document_id,
            fields=0,
        )

    export_path = store.mock_db_exports_dir() / f"{document_id}.json"
    store.save_json(export_path, payload.model_dump(mode="json"))
    return MockDbExportResponse(
        status="exported",
        message="Mock database payload written",
        document_id=document_id,
        export_path=str(export_path),
        fields=len(payload.fields),
    )


def parse_and_optionally_export(
    *,
    store: LocalStore,
    settings: Settings,
    document_id: str,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
    export_after_parse: bool = False,
) -> MockDbExportResponse | None:
    parse_document(
        document_id=document_id,
        store=store,
        settings=settings,
        vlm_provider=vlm_provider,
        vlm_model=vlm_model,
    )
    if not export_after_parse:
        return None
    return export_mock_db_payload(store=store, document_id=document_id)
