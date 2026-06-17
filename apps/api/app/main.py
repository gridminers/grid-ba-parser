from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .batch import export_mock_db_payload, parse_and_optionally_export, register_folder_pdfs
from .config import Settings, get_settings
from .extraction import validate_draft_fields
from .models import (
    BatchScanRequest,
    DocumentDraft,
    JobStatus,
    MockDbExportResponse,
    SearchRequest,
    SearchResponse,
    SyncResult,
    UploadResponse,
    ValidateResult,
    VlmModelsResponse,
    utc_now,
)
from .pipeline import parse_document
from .storage import LocalStore
from .supabase_sync import semantic_search, sync_to_supabase
from .vlm import list_vlm_models

app = FastAPI(title="grid-ba-parser API", version="0.1.0")
settings = get_settings()
store = LocalStore(settings.data_dir)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/artifacts", StaticFiles(directory=settings.data_dir), name="artifacts")


def get_store() -> LocalStore:
    return store


def get_app_settings() -> Settings:
    return settings


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/documents")
def list_documents(local_store: LocalStore = Depends(get_store)):
    return {"documents": local_store.list_documents()}


@app.post("/documents/upload", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    local_store: LocalStore = Depends(get_store),
) -> UploadResponse:
    records = []
    for upload in files:
        if not (upload.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Only PDFs are supported: {upload.filename}")
        records.append(await local_store.create_document_from_upload(upload))
    return UploadResponse(documents=records)


def _run_parse_job(
    job_id: str,
    document_id: str,
    force_vlm_pages: set[int] | None = None,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> None:
    job = store.get_job(job_id)
    job.state = "running"
    job.started_at = utc_now()
    job.message = "rendering and extracting"
    job.progress = 0.2
    job.logs.append("parse started")
    store.save_job(job)
    try:
        parse_document(
            document_id=document_id,
            store=store,
            settings=settings,
            force_vlm_pages=force_vlm_pages,
            vlm_provider=vlm_provider,
            vlm_model=vlm_model,
        )
        job.state = "completed"
        job.progress = 1.0
        job.message = "draft ready"
        job.logs.append("parse completed")
        job.completed_at = utc_now()
    except Exception as exc:
        record = store.get_document(document_id)
        record.status = "failed"
        store.save_document(record)
        job.state = "failed"
        job.error = str(exc)
        job.message = "parse failed"
        job.logs.append(str(exc))
        job.completed_at = utc_now()
    store.save_job(job)


def _run_batch_scan_job(job_id: str, request: BatchScanRequest) -> None:
    job = store.get_job(job_id)
    job.state = "running"
    job.started_at = utc_now()
    job.message = "batch scan running"
    job.progress = 0.05
    job.logs.append("batch scan started")
    store.save_job(job)

    try:
        records = []
        if request.folder_path:
            folder_records = register_folder_pdfs(
                store=store,
                folder_path=Path(request.folder_path),
                recursive=request.recursive,
            )
            records.extend(folder_records)
            job.logs.append(f"registered {len(folder_records)} PDF(s) from folder")

        for document_id in request.document_ids:
            records.append(store.get_document(document_id))

        unique_records = {record.id: record for record in records}
        total = len(unique_records)
        if not total:
            job.message = "no PDFs to scan"
            job.logs.append("no documents found")
        for index, record in enumerate(unique_records.values(), start=1):
            job.message = f"scanning {record.filename}"
            job.progress = min(0.95, index / max(total, 1))
            job.logs.append(f"parsing {record.filename} ({record.id})")
            store.save_job(job)
            export_result = parse_and_optionally_export(
                store=store,
                settings=settings,
                document_id=record.id,
                vlm_provider=request.vlm_provider,
                vlm_model=request.vlm_model,
                export_after_parse=request.export_after_parse,
            )
            if export_result:
                job.logs.append(
                    f"{export_result.status}: {export_result.fields} field(s) -> "
                    f"{export_result.export_path or 'n/a'}"
                )

        job.state = "completed"
        job.progress = 1.0
        job.message = f"batch scan completed: {total} document(s)"
        job.logs.append("batch scan completed")
        job.completed_at = utc_now()
    except Exception as exc:
        job.state = "failed"
        job.error = str(exc)
        job.message = "batch scan failed"
        job.logs.append(str(exc))
        job.completed_at = utc_now()
    store.save_job(job)


@app.post("/documents/{document_id}/parse", response_model=JobStatus)
def parse_endpoint(
    document_id: str,
    background_tasks: BackgroundTasks,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
    local_store: LocalStore = Depends(get_store),
) -> JobStatus:
    try:
        local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    job = JobStatus(id=str(uuid4()), document_id=document_id)
    local_store.save_job(job)
    background_tasks.add_task(_run_parse_job, job.id, document_id, None, vlm_provider, vlm_model)
    return job


@app.post("/batch/scan", response_model=JobStatus)
def batch_scan(
    request: BatchScanRequest,
    background_tasks: BackgroundTasks,
    local_store: LocalStore = Depends(get_store),
) -> JobStatus:
    if not request.document_ids and not request.folder_path:
        raise HTTPException(status_code=400, detail="Provide document_ids or folder_path")
    for document_id in request.document_ids:
        try:
            local_store.get_document(document_id)
        except FileNotFoundError:
            raise _not_found(f"document not found: {document_id}") from None
    job = JobStatus(id=str(uuid4()), document_id="batch", message="queued batch scan")
    local_store.save_job(job)
    background_tasks.add_task(_run_batch_scan_job, job.id, request)
    return job


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str, local_store: LocalStore = Depends(get_store)) -> JobStatus:
    try:
        return local_store.get_job(job_id)
    except FileNotFoundError:
        raise _not_found("job not found") from None


@app.get("/documents/{document_id}/draft", response_model=DocumentDraft)
def get_draft(document_id: str, local_store: LocalStore = Depends(get_store)) -> DocumentDraft:
    try:
        local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    return local_store.get_draft(document_id)


@app.patch("/documents/{document_id}/draft", response_model=DocumentDraft)
def save_draft(
    document_id: str,
    draft: DocumentDraft,
    local_store: LocalStore = Depends(get_store),
) -> DocumentDraft:
    if draft.document_id != document_id:
        raise HTTPException(status_code=400, detail="draft document_id does not match path")
    try:
        local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    return local_store.save_draft(draft)


@app.post("/documents/{document_id}/validate", response_model=ValidateResult)
def validate_draft(document_id: str, draft: DocumentDraft) -> ValidateResult:
    if draft.document_id != document_id:
        return ValidateResult(valid=False, errors=["draft document_id does not match path"])
    errors, warnings = validate_draft_fields(draft.fields)
    return ValidateResult(valid=not errors, errors=errors, warnings=warnings)


@app.post("/documents/{document_id}/sync", response_model=SyncResult)
def sync_document(
    document_id: str,
    local_store: LocalStore = Depends(get_store),
    app_settings: Settings = Depends(get_app_settings),
) -> SyncResult:
    try:
        record = local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    draft = local_store.get_draft(document_id)
    result = sync_to_supabase(settings=app_settings, record=record, draft=draft)
    if result.status == "synced":
        record.status = "synced"
        local_store.save_document(record)
    return result


@app.post("/documents/{document_id}/mock-db-export", response_model=MockDbExportResponse)
def mock_db_export(
    document_id: str,
    local_store: LocalStore = Depends(get_store),
) -> MockDbExportResponse:
    try:
        local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    return export_mock_db_payload(store=local_store, document_id=document_id)


@app.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest,
    app_settings: Settings = Depends(get_app_settings),
) -> SearchResponse:
    return semantic_search(app_settings, request)


@app.get("/vlm/models", response_model=VlmModelsResponse)
def vlm_models(
    provider: str | None = None,
    app_settings: Settings = Depends(get_app_settings),
) -> VlmModelsResponse:
    models, message = list_vlm_models(app_settings, provider)
    selected_provider = provider or app_settings.vlm_provider
    configured_model = {
        "ollama": app_settings.ollama_model,
        "local_vllm": app_settings.local_vllm_model,
        "openai": app_settings.openai_vision_model,
    }.get(selected_provider)
    return VlmModelsResponse(
        provider=selected_provider,
        configured_model=configured_model,
        models=models,
        message=message,
    )


@app.post("/documents/{document_id}/rerun-page", response_model=JobStatus)
def rerun_page(
    document_id: str,
    page: int,
    background_tasks: BackgroundTasks,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
    local_store: LocalStore = Depends(get_store),
) -> JobStatus:
    if page < 1:
        raise HTTPException(status_code=400, detail="page must be >= 1")
    try:
        local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    job = JobStatus(id=str(uuid4()), document_id=document_id, message=f"queued VLM rerun for page {page}")
    local_store.save_job(job)
    background_tasks.add_task(_run_parse_job, job.id, document_id, {page}, vlm_provider, vlm_model)
    return job


@app.get("/documents/{document_id}/artifact-text")
def read_artifact_text(document_id: str, path: str, local_store: LocalStore = Depends(get_store)):
    try:
        local_store.get_document(document_id)
    except FileNotFoundError:
        raise _not_found("document not found") from None
    target = Path(path).resolve()
    data_root = local_store.data_dir.resolve()
    if data_root not in target.parents and target != data_root:
        raise HTTPException(status_code=400, detail="artifact path outside data directory")
    if not target.exists():
        raise _not_found("artifact not found")
    return {"path": str(target), "text": target.read_text(encoding="utf-8", errors="replace")}
