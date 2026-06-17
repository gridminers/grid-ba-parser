from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


FieldSource = Literal["embedded_text", "ocr", "heuristic", "vlm", "reviewer"]
JobState = Literal["queued", "running", "completed", "failed"]
DocumentStatus = Literal["uploaded", "parsing", "draft", "synced", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WarningItem(BaseModel):
    code: str
    message: str
    page: int | None = None
    severity: Literal["info", "warning", "error"] = "warning"


class ExtractedField(BaseModel):
    label: str
    value_raw: str | None = None
    value_normalized: str | None = None
    type: str = "text"
    section: str | None = None
    page: int
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bbox: list[float] | None = None
    evidence: str | None = None
    source: FieldSource = "heuristic"

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and len(value) != 4:
            raise ValueError("bbox must contain four numbers")
        return value


class ExtractedTable(BaseModel):
    title: str | None = None
    page: int
    rows: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: FieldSource = "heuristic"


class PageArtifact(BaseModel):
    page: int
    image_path: str | None = None
    image_url: str | None = None
    text_path: str | None = None
    vlm_response_path: str | None = None
    route: str = "local"
    quality_score: float = 0.0
    ocr_confidence: float | None = None
    warnings: list[WarningItem] = Field(default_factory=list)


class DocumentDraft(BaseModel):
    document_id: str
    language: str = "de"
    fields: list[ExtractedField] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    pages: list[PageArtifact] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    raw_text: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    sha256: str
    status: DocumentStatus = "uploaded"
    source_path: str
    draft_path: str | None = None
    page_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    warnings: list[WarningItem] = Field(default_factory=list)


class JobStatus(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    state: JobState = "queued"
    message: str = "queued"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class UploadResponse(BaseModel):
    documents: list[DocumentRecord]


class BatchScanRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    folder_path: str | None = None
    recursive: bool = False
    vlm_provider: str | None = None
    vlm_model: str | None = None
    export_after_parse: bool = False


class MockDbField(BaseModel):
    label: str
    sanitized_value: str | None = None
    value_normalized: str | None = None
    value_raw: str | None = None
    type: str = "text"
    page: int
    confidence: float = 0.0
    source: FieldSource = "heuristic"


class MockDbExportPayload(BaseModel):
    document_id: str
    filename: str
    sha256: str
    exported_at: datetime = Field(default_factory=utc_now)
    fields: list[MockDbField] = Field(default_factory=list)


class MockDbExportResponse(BaseModel):
    status: Literal["exported", "skipped", "failed"]
    message: str
    document_id: str
    export_path: str | None = None
    fields: int = 0


class ValidateResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SyncResult(BaseModel):
    status: Literal["synced", "skipped", "failed"]
    message: str
    document_id: str
    chunks: int = 0
    embeddings: int = 0


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


class SearchHit(BaseModel):
    document_id: str
    chunk_id: str
    content: str
    similarity: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    hits: list[SearchHit] = Field(default_factory=list)
    message: str = ""


class VlmModelInfo(BaseModel):
    id: str
    provider: str
    installed: bool = True
    vision_likely: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class VlmModelsResponse(BaseModel):
    provider: str
    configured_model: str | None = None
    models: list[VlmModelInfo] = Field(default_factory=list)
    message: str = ""
