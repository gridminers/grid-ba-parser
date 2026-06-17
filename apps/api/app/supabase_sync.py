from uuid import uuid4

from .config import Settings
from .models import DocumentDraft, DocumentRecord, SearchHit, SearchRequest, SearchResponse, SyncResult


def _chunk_draft(draft: DocumentDraft) -> list[str]:
    lines: list[str] = []
    for field in draft.fields:
        lines.append(
            f"{field.label}: {field.value_normalized or field.value_raw or ''} "
            f"(page {field.page}, source {field.source})"
        )
    for table in draft.tables:
        lines.append(f"Table {table.title or ''} page {table.page}: {table.rows}")
    content = "\n".join(lines).strip()
    if not content:
        return []
    max_chars = 5000
    return [content[index : index + max_chars] for index in range(0, len(content), max_chars)]


def sync_to_supabase(
    *,
    settings: Settings,
    record: DocumentRecord,
    draft: DocumentDraft,
) -> SyncResult:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return SyncResult(
            status="skipped",
            message="Supabase credentials are not configured",
            document_id=record.id,
        )

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    client.table("documents").upsert(
        {
            "id": record.id,
            "filename": record.filename,
            "sha256": record.sha256,
            "status": "synced",
            "page_count": record.page_count,
            "draft": draft.model_dump(mode="json"),
        }
    ).execute()

    client.table("pages").delete().eq("document_id", record.id).execute()
    if draft.pages:
        client.table("pages").insert(
            [
                {
                    "document_id": record.id,
                    "page_number": page.page,
                    "route": page.route,
                    "quality_score": page.quality_score,
                    "ocr_confidence": page.ocr_confidence,
                    "text_content": None,
                    "image_uri": page.image_path,
                    "warnings": [item.model_dump(mode="json") for item in page.warnings],
                }
                for page in draft.pages
            ]
        ).execute()

    client.table("extracted_fields").delete().eq("document_id", record.id).execute()
    if draft.fields:
        client.table("extracted_fields").insert(
            [
                {
                    "document_id": record.id,
                    "label": field.label,
                    "value_raw": field.value_raw,
                    "value_normalized": field.value_normalized,
                    "value_type": field.type,
                    "section": field.section,
                    "page": field.page,
                    "confidence": field.confidence,
                    "bbox": field.bbox,
                    "evidence": field.evidence,
                    "source": field.source,
                    "reviewer_state": "approved",
                }
                for field in draft.fields
            ]
        ).execute()

    client.table("extracted_tables").delete().eq("document_id", record.id).execute()
    if draft.tables:
        client.table("extracted_tables").insert(
            [
                {
                    "document_id": record.id,
                    "title": table.title,
                    "page": table.page,
                    "rows": table.rows,
                    "confidence": table.confidence,
                    "source": table.source,
                }
                for table in draft.tables
            ]
        ).execute()

    chunks = _chunk_draft(draft)
    client.table("document_chunks").delete().eq("document_id", record.id).execute()
    client.table("document_embeddings").delete().eq("document_id", record.id).execute()
    chunk_records = [
        {
            "id": str(uuid4()),
            "document_id": record.id,
            "chunk_index": index,
            "content": chunk,
            "metadata": {"source": "approved_extraction"},
        }
        for index, chunk in enumerate(chunks)
    ]
    if chunk_records:
        client.table("document_chunks").insert(chunk_records).execute()

    embeddings_count = 0
    if settings.openai_api_key and chunks:
        from openai import OpenAI

        openai_client = OpenAI(api_key=settings.openai_api_key)
        response = openai_client.embeddings.create(
            model=settings.openai_embedding_model,
            input=chunks,
            encoding_format="float",
        )
        embeddings = [
            {
                "chunk_id": chunk_records[item.index]["id"],
                "document_id": record.id,
                "embedding": item.embedding,
                "model": settings.openai_embedding_model,
            }
            for item in response.data
        ]
        if embeddings:
            client.table("document_embeddings").insert(embeddings).execute()
            embeddings_count = len(embeddings)

    return SyncResult(
        status="synced",
        message="Document synced to Supabase",
        document_id=record.id,
        chunks=len(chunks),
        embeddings=embeddings_count,
    )


def semantic_search(settings: Settings, request: SearchRequest) -> SearchResponse:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return SearchResponse(message="Supabase credentials are not configured")
    if not settings.openai_api_key:
        return SearchResponse(message="OpenAI API key is not configured")

    from openai import OpenAI
    from supabase import create_client

    openai_client = OpenAI(api_key=settings.openai_api_key)
    embedding_response = openai_client.embeddings.create(
        model=settings.openai_embedding_model,
        input=request.query,
        encoding_format="float",
    )
    embedding = embedding_response.data[0].embedding

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    response = client.rpc(
        "match_document_chunks",
        {"query_embedding": embedding, "match_count": request.top_k},
    ).execute()
    rows = response.data or []
    hits = [
        SearchHit(
            document_id=str(row["document_id"]),
            chunk_id=str(row["chunk_id"]),
            content=row["content"],
            similarity=float(row["similarity"]),
            metadata=row.get("metadata") or {},
        )
        for row in rows
    ]
    return SearchResponse(hits=hits, message=f"{len(hits)} hit(s)")
