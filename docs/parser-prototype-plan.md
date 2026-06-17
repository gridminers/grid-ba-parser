# Technical PDF Extraction Prototype Plan

## Purpose

This repository is a technical extraction workbench for German historical planning approval PDFs. It is not the final visualization, analytics, or presentation application. The main job is to turn irregular, sometimes non-OCRable PDFs into editable flexible key-value JSON and then sync approved records to Supabase/Postgres.

## Architecture

- `apps/api` is the source of truth for ingestion, rendering, OCR, VLM fallback, validation, local drafts, and Supabase sync.
- `apps/web` is a minimal operator console for upload, parse, JSON review, debug inspection, export, and sync.
- `supabase/schema.sql` defines normalized storage for documents, pages, extraction runs, key-value fields, table blocks, chunks, and embeddings.

The extraction pipeline uses a hybrid approach:

1. Compute a SHA-256 hash for each uploaded PDF and deduplicate by hash.
2. Render each page to an image with PyMuPDF.
3. Extract embedded text with PyMuPDF.
4. Run optional local OCR with Tesseract when available.
5. Score page quality by text volume, OCR confidence, key field signals, table/currency signals, and checkbox density.
6. Send low-confidence or explicitly requested pages to GPT-5.5 vision when OpenAI credentials are available.
7. Merge local and VLM candidates into a draft JSON document.
8. Let a technical reviewer edit and validate the draft.
9. Sync approved data to Supabase and create embeddings for future semantic search.

## Draft JSON

Drafts are flexible and intentionally preserve uncertainty:

```json
{
  "document_id": "uuid",
  "language": "de",
  "fields": [
    {
      "label": "PSP-Element",
      "value_raw": "2H.02.1224.104.012",
      "value_normalized": "2H.02.1224.104.012",
      "type": "identifier",
      "section": "Kontierung",
      "page": 1,
      "confidence": 0.93,
      "bbox": [123, 456, 789, 512],
      "evidence": "visible label/value snippet",
      "source": "vlm"
    }
  ],
  "tables": [],
  "warnings": []
}
```

## Operator Console

The web app is deliberately sparse:

- Upload one or more PDFs.
- Select a document and start or rerun parsing.
- Poll parse jobs and expose logs/errors.
- Edit raw JSON directly.
- Inspect key-value rows, page routes, OCR text, VLM responses, and page images.
- Validate, save draft, export JSON/CSV, and sync approved data.

Out of scope: charts, dashboards, business presentation views, analytics narratives, and polished reviewer workflows.

## Supabase

Run `supabase/schema.sql` in the Supabase SQL editor. The schema enables `vector`, stores the approved extraction results, and keeps `document_embeddings` separate from raw extracted fields so embeddings can be rebuilt without rewriting the extraction record.

Embeddings are generated only from approved/synced draft content.

## Test Strategy

- Unit tests cover German date/currency normalization and key-field extraction.
- Pipeline tests should use fixture PDFs for OCRable, scanned, mixed-layout, checkbox-heavy, and table-heavy documents.
- Integration tests should mock OpenAI and Supabase clients.
- Manual acceptance is upload -> parse -> edit JSON -> validate -> save -> export -> sync.
