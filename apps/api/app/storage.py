import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from .models import DocumentDraft, DocumentRecord, JobStatus, utc_now


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class LocalStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.documents_dir = data_dir / "documents"
        self.jobs_dir = data_dir / "jobs"
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self, document_id: str) -> Path:
        return self.documents_dir / document_id / "metadata.json"

    def document_dir(self, document_id: str) -> Path:
        path = self.documents_dir / document_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def pages_dir(self, document_id: str) -> Path:
        path = self.document_dir(document_id) / "pages"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def draft_path(self, document_id: str) -> Path:
        return self.document_dir(document_id) / "draft.json"

    def mock_db_exports_dir(self) -> Path:
        path = self.data_dir / "mock_db_exports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def list_documents(self) -> list[DocumentRecord]:
        records: list[DocumentRecord] = []
        for path in sorted(self.documents_dir.glob("*/metadata.json")):
            records.append(DocumentRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def find_by_sha256(self, sha256: str) -> DocumentRecord | None:
        for record in self.list_documents():
            if record.sha256 == sha256:
                return record
        return None

    async def create_document_from_upload(self, upload: UploadFile) -> DocumentRecord:
        content = await upload.read()
        sha256 = sha256_bytes(content)
        existing = self.find_by_sha256(sha256)
        if existing:
            return existing

        filename = Path(upload.filename or "document.pdf").name
        record = DocumentRecord(filename=filename, sha256=sha256, source_path="")
        doc_dir = self.document_dir(record.id)
        source_path = doc_dir / filename
        source_path.write_bytes(content)
        record.source_path = str(source_path)
        self.save_document(record)
        return record

    def create_document_from_path(self, pdf_path: Path) -> DocumentRecord:
        content = pdf_path.read_bytes()
        sha256 = sha256_bytes(content)
        existing = self.find_by_sha256(sha256)
        if existing:
            return existing

        filename = pdf_path.name
        record = DocumentRecord(filename=filename, sha256=sha256, source_path="")
        doc_dir = self.document_dir(record.id)
        source_path = doc_dir / filename
        source_path.write_bytes(content)
        record.source_path = str(source_path)
        self.save_document(record)
        return record

    def save_document(self, record: DocumentRecord) -> DocumentRecord:
        record.updated_at = utc_now()
        path = self._metadata_path(record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def get_document(self, document_id: str) -> DocumentRecord:
        path = self._metadata_path(document_id)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {document_id}")
        return DocumentRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save_draft(self, draft: DocumentDraft) -> DocumentDraft:
        draft.updated_at = utc_now()
        path = self.draft_path(draft.document_id)
        path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
        record = self.get_document(draft.document_id)
        record.draft_path = str(path)
        record.status = "draft"
        self.save_document(record)
        return draft

    def get_draft(self, document_id: str) -> DocumentDraft:
        path = self.draft_path(document_id)
        if not path.exists():
            return DocumentDraft(document_id=document_id)
        return DocumentDraft.model_validate_json(path.read_text(encoding="utf-8"))

    def save_json(self, path: Path, payload: dict[str, Any] | list[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def save_job(self, job: JobStatus) -> JobStatus:
        self.job_path(job.id).write_text(job.model_dump_json(indent=2), encoding="utf-8")
        return job

    def get_job(self, job_id: str) -> JobStatus:
        path = self.job_path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job not found: {job_id}")
        return JobStatus.model_validate_json(path.read_text(encoding="utf-8"))

    def artifact_url(self, path: str | Path) -> str:
        full_path = Path(path).resolve()
        rel = full_path.relative_to(self.data_dir.resolve()).as_posix()
        return f"/artifacts/{rel}"

    def clear_pages(self, document_id: str) -> None:
        pages_dir = self.pages_dir(document_id)
        if pages_dir.exists():
            shutil.rmtree(pages_dir)
        pages_dir.mkdir(parents=True, exist_ok=True)
