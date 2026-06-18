# grid-ba-parser

Technical workbench for extracting flexible key-value data from unstructured German infrastructure approval PDFs.

The project contains:

- `apps/api` - FastAPI ingestion, PDF rendering, OCR, hybrid VLM extraction, validation, and Supabase sync.
- `apps/web` - Minimal technical operator console for upload, parse jobs, JSON editing, debug artifacts, and sync.
- `supabase/schema.sql` - Postgres/Supabase schema, including pgvector tables for approved chunks.
- `docs/parser-prototype-plan.md` - Architecture and implementation plan.

## Screenshots
<img width="1841" height="1033" alt="image" src="https://github.com/user-attachments/assets/45bd4729-aa69-4558-bc84-eb482a4bdcb5" />


## Current Feature Status

### Implemented

- Single PDF upload, multiple PDF upload, and browser folder PDF upload from the web UI.
- Server-folder batch scan through the UI and `POST /batch/scan`.
- Cron-friendly batch scan script at `apps/api/scripts/scan_and_export.py`.
- PDF rendering and embedded text extraction through PyMuPDF.
- Optional OCR through Tesseract when the local `tesseract` binary is installed.
- OCR layout hints with bounding boxes when Tesseract is available, so the VLM receives more than plain line-by-line text.
- VLM extraction through three providers: hosted OpenAI, local Ollama, and local vLLM.
- Prompting for the 19 priority fields: `Projekttitel`, `Geschäftsjahr`, `Ausführungszeit`, `Antragsgrund`, `Sparte`, `Asset`, `PSP-Element`, `Leitungsmeter`, `Euro pro Meter Trassenlänge`, cost fields, surcharge fields, `Gesamtkosten`, and `Zahlungsplan`.
- Editable draft JSON output with page-level debug artifacts.
- Saved VLM debug JSON containing `provider`, `model`, `prompt`, and `raw_response`.
- Mock database export from the UI with `Send to DB (mock)`.
- Mock database export from the API with `POST /documents/{document_id}/mock-db-export`.
- Mock database export from cron/batch scans when export-after-parse is enabled.
- Example mock export payload tracked in `mock_db_exports/08b48c1e-d7ee-46b5-a574-5d73ec9d550f.json` for the API team.
- Supabase schema and sync path, enabled only when Supabase credentials are configured.

### Not Implemented Or Still Mocked

- The final database write API is not connected yet. `Send to DB (mock)` writes a local JSON file instead.
- Production authentication, authorization, and user management are not included.
- A managed scheduler service is not included. Use the documented cron command for automatic folder scans.
- Tesseract is not bundled with the app. It must be installed on the host machine.
- VLM model availability is external. OpenAI depends on the API key/account model access, Ollama depends on locally pulled models, and vLLM depends on the local server.
- The parser does not learn automatically from manual corrections yet.
- Extraction is not guaranteed to be perfect for every non-uniform PDF. The current workflow expects operator review of draft JSON and debug artifacts.
- The browser cannot scan arbitrary server folders directly. `Scan server folder` only works for paths visible to the API process.

## Fresh Local Setup Checklist

These commands assume Linux or WSL2 from the repository root. Windows PowerShell commands are shown later in provider-specific sections.

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Create and install the API environment:

```bash
python3 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install --upgrade pip
apps/api/.venv/bin/pip install -e 'apps/api[dev]'
```

3. Install Tesseract for better OCR and bounding-box layout hints:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng
```

4. Install web dependencies. If the system already has Node.js 22+ and npm, use:

```bash
npm --prefix apps/web install
```

If Node is not installed, use a local Node runtime inside the repo:

```bash
mkdir -p .local-tools
curl -fsSL https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-x64.tar.xz \
  -o .local-tools/node-v22.12.0-linux-x64.tar.xz
tar -xJf .local-tools/node-v22.12.0-linux-x64.tar.xz -C .local-tools
PATH="$PWD/.local-tools/node-v22.12.0-linux-x64/bin:$PATH" npm --prefix apps/web install
```

5. Configure `.env` for one VLM provider:

```env
# Hosted OpenAI
VLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_VISION_MODEL=gpt-5.5
API_ENABLE_VLM=true
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

For local Ollama or local vLLM, use the provider-specific sections below.

6. Start the API:

```bash
mkdir -p logs
PYTHONUNBUFFERED=1 apps/api/.venv/bin/python -m uvicorn app.main:app \
  --reload \
  --app-dir apps/api \
  --host 127.0.0.1 \
  --port 8000 \
  2>&1 | tee -a logs/api.log
```

7. Start the web UI in another terminal:

```bash
mkdir -p logs
PATH="$PWD/.local-tools/node-v22.12.0-linux-x64/bin:$PATH" \
NEXT_PUBLIC_API_BASE=http://localhost:8000 \
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000 \
  2>&1 | tee -a logs/web.log
```

8. Open the app:

```text
http://127.0.0.1:3000
```

9. Verify the running services:

```bash
curl http://127.0.0.1:8000/health
curl -I http://127.0.0.1:3000
curl "http://127.0.0.1:8000/vlm/models?provider=openai"
```

10. Watch logs while parsing:

```bash
tail -f logs/api.log logs/web.log
```

## Quick Start

```powershell
Copy-Item .env.example .env

# API
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
uvicorn app.main:app --reload

# Web, in another terminal
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000` for the technical console. The API runs on `http://localhost:8000`.

## Docker Run

The app can run locally with Docker Compose as two long-running services plus one optional scanner job:

- `api` - FastAPI parser backend on port `8000`.
- `web` - Next.js operator UI on port `3000`.
- `scanner` - one-off batch scanner that reads PDFs from `docker-data/incoming`.

Create the local shared data folders:

```bash
mkdir -p docker-data/incoming docker-data/documents docker-data/mock_db_exports
```

Configure `.env` before starting the containers. For OpenAI:

```env
VLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_VISION_MODEL=gpt-5.5
API_ENABLE_VLM=true
API_DATA_DIR=/data
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Build and run the API and web UI:

```bash
docker compose up --build api web
```

Open:

```text
http://localhost:3000
```

Verify the API:

```bash
curl http://localhost:8000/health
```

To scan PDFs without the UI, place files in:

```text
docker-data/incoming/
```

Then run the scanner job:

```bash
docker compose run --rm scanner
```

Mock database export JSON files are written to:

```text
docker-data/mock_db_exports/
```

For host cron, run the scanner on a schedule:

```cron
*/10 * * * * cd /path/to/grid-ba-parser && docker compose run --rm scanner >> logs/docker-cron.log 2>&1
```

The Docker API image includes Tesseract with German and English OCR language packages. The same image can be used in AWS ECS as the API service and as the scheduled scanner task.

## Runtime Notes

- Local PDF text extraction and rendering use PyMuPDF.
- OCR uses `pytesseract` if the Tesseract binary is installed locally; otherwise pages can still fall back to VLM.
- Hosted OpenAI VLM extraction is enabled when `VLM_PROVIDER=openai` and `OPENAI_API_KEY` are configured.
- Local vLLM extraction is enabled when `VLM_PROVIDER=local_vllm` and a vLLM OpenAI-compatible server is running.
- Local Ollama extraction is enabled when `VLM_PROVIDER=ollama` and Ollama is running on your machine.
- Supabase sync is enabled when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are configured.
- Approved embeddings use `text-embedding-3-small` by default and are stored in Supabase/Postgres via pgvector.

This is intentionally not a polished analytics app. It is a technical extraction console for operators comfortable with raw JSON and unstructured data.

## Batch PDF Scans And Mock Database Export

The parser supports three batch-style paths:

1. Upload multiple PDFs with the existing file picker.
2. Upload all PDFs from a browser-selected folder with `Upload folder PDFs`.
3. Scan a server-visible folder path, which is the same mode used by cron jobs.

Batch scans use the same extraction pipeline as a single-document parse. That means the selected VLM provider, OCR text, rendered page images, layout hints, target-field prompt, draft JSON, and debug artifacts are all produced in the same format.

The real database endpoint is intentionally not wired yet. Until that endpoint is decided, `Mock DB export` writes the payload that would be sent to a database as JSON under:

```text
<API_DATA_DIR>/mock_db_exports/<document-id>.json
```

If `API_DATA_DIR` is not set, the default is `apps/api/data`. If `API_DATA_DIR=.` is set, output folders are created at the repo root.

Each mock export contains document metadata plus the extracted key/value pair as `label` and `sanitized_value`. The export also keeps `value_normalized`, `value_raw`, `type`, `page`, `confidence`, and `source` for debugging and traceability.

Example mock export shape:

```json
{
  "document_id": "365aebe0-5c69-405f-aeb9-31794cd66dea",
  "filename": "example.pdf",
  "sha256": "...",
  "exported_at": "2026-06-17T13:00:00Z",
  "fields": [
    {
      "label": "PSP-Element",
      "sanitized_value": "2H.02.1224.104.012",
      "value_normalized": "2H.02.1224.104.012",
      "value_raw": "2H.02.1224.104.012",
      "type": "identifier",
      "page": 1,
      "confidence": 0.92,
      "source": "vlm"
    }
  ]
}
```

### UI Batch Scan

1. Start the API and web UI.
2. Use `Upload PDFs` to select multiple PDFs, or `Batch Scan -> Upload folder PDFs` to choose a folder from your browser.
3. Select the VLM provider/model.
4. Keep `Send to DB after scan (mock)` checked if you want JSON files written after parsing.
5. Click `Parse all uploaded`.

For a server-side folder path that the API process can read:

1. Enter an absolute path in `Server folder path for cron-style scans`.
2. Optionally enable `Recursive`.
3. Click `Scan server folder`.

Browser folder upload and server folder scan are different:

- `Upload folder PDFs` reads files from your browser and uploads them to the API.
- `Scan server folder` reads a path from the machine running the API. Use this for folders watched by cron or shared mounted drives.

### Manual Mock DB Export

After a document has a draft, click:

```text
Send to DB (mock)
```

This writes the selected document's `label` and `sanitized_value` payload to `<API_DATA_DIR>/mock_db_exports/`.

You can trigger the same export from the command line:

```bash
export DOC_ID=replace-with-document-id

curl -X POST "http://127.0.0.1:8000/documents/$DOC_ID/mock-db-export"
```

### Cron-Friendly Folder Scan

The CLI script scans a folder for PDFs, registers new PDFs by SHA-256, parses them, and writes mock DB export JSON files. Existing documents with an export file are skipped by default, so repeated cron runs focus on newly added PDFs.

Run once:

```bash
apps/api/.venv/bin/python apps/api/scripts/scan_and_export.py \
  --folder /absolute/path/to/pdf-folder \
  --recursive \
  --vlm-provider openai \
  --vlm-model gpt-5.5
```

Force reprocessing of PDFs that were already exported:

```bash
apps/api/.venv/bin/python apps/api/scripts/scan_and_export.py \
  --folder /absolute/path/to/pdf-folder \
  --recursive \
  --rescan-existing
```

Example crontab entry, every 10 minutes:

```cron
*/10 * * * * cd /home/rosy-akapor/Documents/grid-ba-parser && apps/api/.venv/bin/python apps/api/scripts/scan_and_export.py --folder /absolute/path/to/pdf-folder --recursive --vlm-provider openai --vlm-model gpt-5.5 >> logs/cron-scan.log 2>&1
```

Cron does not require the web UI or FastAPI server. It imports the parser directly, uses `.env`, writes drafts/artifacts under `<API_DATA_DIR>/documents/`, and writes mock DB payloads under `<API_DATA_DIR>/mock_db_exports/`.

Useful cron log check:

```bash
tail -f logs/cron-scan.log
```

### Batch API Endpoints

Queue a batch scan for already uploaded documents:

```bash
curl -X POST "http://127.0.0.1:8000/batch/scan" \
  -H "content-type: application/json" \
  -d '{
    "document_ids": ["replace-with-document-id"],
    "vlm_provider": "openai",
    "vlm_model": "gpt-5.5",
    "export_after_parse": true
  }'
```

Queue a batch scan for a server-visible folder:

```bash
curl -X POST "http://127.0.0.1:8000/batch/scan" \
  -H "content-type: application/json" \
  -d '{
    "folder_path": "/absolute/path/to/pdf-folder",
    "recursive": true,
    "vlm_provider": "openai",
    "vlm_model": "gpt-5.5",
    "export_after_parse": true
  }'
```

Both calls return a job ID:

```json
{
  "id": "replace-with-job-id",
  "document_id": "batch",
  "state": "queued",
  "message": "queued batch scan"
}
```

Poll the batch job:

```bash
export JOB_ID=replace-with-job-id
curl "http://127.0.0.1:8000/jobs/$JOB_ID"
```

### Batch Troubleshooting

- If `Scan server folder` finds nothing, confirm the path is visible to the API process, not just the browser.
- If repeated cron runs skip a file, an export JSON already exists for that document ID. Use `--rescan-existing` to force reprocessing.
- If files are uploaded but not parsed, use `Parse all uploaded` or call `/batch/scan` with `document_ids`.
- If no mock DB JSON appears, confirm the draft has fields and check `logs/api.log` or `logs/cron-scan.log`.

### End-To-End Verification Checklist

After starting the API and UI, verify each layer:

```bash
curl http://127.0.0.1:8000/health
```

The UI is reachable when this returns `200 OK`:

```bash
curl -I http://127.0.0.1:3000
```

The OpenAI provider is visible when this returns `provider: openai` and the configured model:

```bash
curl "http://127.0.0.1:8000/vlm/models?provider=openai"
```

The `Parse` button sends:

```text
POST /documents/<document-id>/parse?vlm_provider=<provider>&vlm_model=<model>
```

Confirm it in the API log:

```bash
tail -f logs/api.log
```

After a successful VLM parse, inspect:

```bash
find apps/api/data/documents documents -name "*.vlm.json" -print 2>/dev/null
```

The file should include `provider`, `model`, `prompt`, and `raw_response`.

## Local Run With OpenAI Vision Logging

Use this checklist when you want to prove that the hosted OpenAI vision path is being called, see the exact prompt with the 19 target fields, and inspect the raw model response.

### 1. Stop Existing Local App Processes

From the repo root:

```bash
pkill -f "uvicorn app.main:app" || true
pkill -f "next dev" || true
```

Confirm the API and web server are stopped:

```bash
pgrep -af "uvicorn app.main:app|next dev" || echo "API and web are stopped"
```

### 2. Configure `.env`

For an OpenAI-only test, set these values in `.env`:

```env
OPENAI_API_KEY=sk-your-key
OPENAI_VISION_MODEL=gpt-5.5
VLM_PROVIDER=openai
API_ENABLE_VLM=true
API_LOW_CONFIDENCE_THRESHOLD=1
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

`API_LOW_CONFIDENCE_THRESHOLD=1` forces every page through the selected VLM provider during parsing, which makes it easier to verify that OpenAI is being used.

### 3. Verify The OpenAI Key

This command checks the key without printing it:

```bash
apps/api/.venv/bin/python - <<'PY'
import sys
import httpx
from dotenv import dotenv_values

values = dotenv_values(".env")
key = values.get("OPENAI_API_KEY") or ""
print("OPENAI_API_KEY present:", "yes" if key else "no")
print("OPENAI_API_KEY length:", len(key) if key else 0)
print("OPENAI_API_KEY prefix:", (key[:7] + "...") if key else "n/a")
print("OPENAI_VISION_MODEL:", values.get("OPENAI_VISION_MODEL"))
if not key:
    sys.exit(2)

response = httpx.get(
    "https://api.openai.com/v1/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=20,
)
print("OpenAI auth HTTP status:", response.status_code)
data = response.json()
if response.is_success:
    print("OpenAI auth OK; models returned:", len(data.get("data", [])))
else:
    error = data.get("error", {})
    print("OpenAI auth error:", error.get("type"), error.get("code"), "-", error.get("message"))
    sys.exit(1)
PY
```

You should see `OpenAI auth HTTP status: 200`.

### 4. Start The API With Logs

Terminal 1:

```bash
mkdir -p logs
PYTHONUNBUFFERED=1 apps/api/.venv/bin/python -m uvicorn app.main:app \
  --reload \
  --app-dir apps/api \
  --host 127.0.0.1 \
  --port 8000 \
  2>&1 | tee -a logs/api.log
```

### 5. Start The Web UI With Logs

Terminal 2:

```bash
mkdir -p logs
PATH="$PWD/.local-tools/node-v22.12.0-linux-x64/bin:$PATH" \
NEXT_PUBLIC_API_BASE=http://localhost:8000 \
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000 \
  2>&1 | tee -a logs/web.log
```

Open `http://127.0.0.1:3000`.

Watch both logs from a third terminal:

```bash
tail -f logs/api.log logs/web.log
```

### 6. Verify The Provider In The UI

1. Select `OpenAI hosted`.
2. Click `Refresh models`.
3. Confirm the model dropdown shows the configured OpenAI model.
4. Upload a PDF, or select an existing document.
5. Click `Parse`, or use `Re-run page with VLM` for a single-page test.
6. After the job completes, the page debug card route should show `openai`.
7. Click `View VLM JSON` to inspect the exact prompt and raw response.

The saved VLM JSON should include:

```json
{
  "provider": "openai",
  "prompt": "...19 target fields...",
  "raw_response": "...",
  "model": "gpt-5.5"
}
```

### 7. Force OpenAI From The Command Line

If you already have a document ID, you can bypass the UI and force OpenAI parsing:

```bash
export DOC_ID=replace-with-document-id

curl -X POST \
  "http://127.0.0.1:8000/documents/$DOC_ID/parse?vlm_provider=openai&vlm_model=gpt-5.5"
```

The response contains a job ID. Poll it until `state` is `completed`:

```bash
JOB_ID=replace-with-job-id

curl "http://127.0.0.1:8000/jobs/$JOB_ID"
```

For one page only:

```bash
export DOC_ID=replace-with-document-id
PAGE=1

curl -X POST \
  "http://127.0.0.1:8000/documents/$DOC_ID/rerun-page?page=$PAGE&vlm_provider=openai&vlm_model=gpt-5.5"
```

Inspect the saved prompt and raw OpenAI response:

```bash
find "documents/$DOC_ID/pages" -name "*.vlm.json" -print
apps/api/.venv/bin/python -m json.tool "documents/$DOC_ID/pages/page-001.vlm.json" | less
```

Check only the provider/model/prompt fields:

```bash
export DOC_ID=replace-with-document-id

apps/api/.venv/bin/python - <<'PY'
import os
import json
from pathlib import Path

doc_id = os.environ["DOC_ID"]
path = Path("documents") / doc_id / "pages" / "page-001.vlm.json"
data = json.loads(path.read_text(encoding="utf-8"))
print("provider:", data.get("provider"))
print("model:", data.get("model"))
print("prompt contains Projekttitel:", "Projekttitel" in data.get("prompt", ""))
print("prompt contains Zahlungsplan:", "Zahlungsplan" in data.get("prompt", ""))
print("raw response chars:", len(data.get("raw_response", "")))
PY
```

### Troubleshooting OpenAI Routing

- If the route still shows `ollama`, make sure the UI provider dropdown is set to `OpenAI hosted`, or pass `vlm_provider=openai` in the curl command.
- If no `.vlm.json` file is created, check `logs/api.log` and the job error from `/jobs/{job_id}`.
- If OpenAI auth passes but parsing fails, verify `OPENAI_VISION_MODEL` is a vision-capable model available to your account.
- If parsing uses local extraction instead of VLM, set `API_LOW_CONFIDENCE_THRESHOLD=1` and restart the API.

## No API Key Local Vision Testing

You do not need Ollama if you already have vLLM running. But if you do not have an OpenAI API key and simply want to test how PDF pages are parsed by a local vision model, Ollama is usually the easiest starting point.

For vLLM on this Windows project, use Ubuntu/WSL2 instead of native Windows. See [docs/local-vlm-ubuntu.md](docs/local-vlm-ubuntu.md) for the project-specific setup, ports, and `.env` values.

The app now supports three VLM providers:

- `ollama` - easiest local no-key test path.
- `local_vllm` - better for GPU/server-style experiments and OpenAI-compatible serving.
- `openai` - hosted GPT-5.5 path, requires `OPENAI_API_KEY`.

The web console includes a VLM provider dropdown and a model dropdown. For Ollama it calls `GET /api/tags` and shows installed models that look like vision models first. If no model can be confidently identified as vision-capable, it shows all installed models so you can still choose manually.

### Ollama Quick Start

Install Ollama from [ollama.com/download](https://ollama.com/download), then pull a vision model:

```powershell
ollama pull qwen2.5vl
```

Other local vision models you can try:

```powershell
ollama pull qwen3-vl
ollama pull llava
ollama pull gemma4
```

Model availability depends on your Ollama version and hardware. For document screenshots, Qwen vision models are usually a good first test.

Confirm Ollama is running:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags
```

Set `.env`:

```env
VLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5vl
OLLAMA_TEMPERATURE=0
API_ENABLE_VLM=true
```

Restart the API after changing `.env`.

In the web console:

1. Select `Ollama local` in the VLM provider dropdown.
2. Click `Refresh models`.
3. Pick an installed vision model.
4. Upload a PDF.
5. Click `Parse`, or force one page through the selected model with `Re-run page with VLM`.

To force every page through the selected local model during testing:

```env
API_LOW_CONFIDENCE_THRESHOLD=1
```

Ollama references:

- [Ollama API base URL](https://docs.ollama.com/api/introduction)
- [Ollama list installed models](https://docs.ollama.com/api/tags)
- [Ollama structured outputs with vision](https://docs.ollama.com/capabilities/structured-outputs)
- [Ollama qwen2.5vl model page](https://ollama.com/library/qwen2.5vl)

## Local vLLM Test Mode

Use this when you want to test PDF page extraction with a local vision-language model instead of sending page images to OpenAI.

vLLM provides an OpenAI-compatible HTTP server with chat completions and multimodal image inputs. The parser uses that local Chat Completions endpoint when `VLM_PROVIDER=local_vllm`.

Useful docs:

- [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/v0.19.0/serving/openai_compatible_server/)
- [vLLM multimodal OpenAI client example](https://docs.vllm.ai/en/v0.7.3/getting_started/examples/openai_chat_completion_client_for_multimodal.html)
- [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)

### 1. Start vLLM

vLLM is best run on Linux/WSL2 or Docker with an NVIDIA GPU. On Windows, run this in WSL2 unless you already have a working Linux GPU environment.

Use a separate port from the FastAPI app. The API uses `8000`, so this example uses `8001`.

```bash
python -m venv .venv-vllm
source .venv-vllm/bin/activate
pip install --upgrade pip
pip install vllm

vllm serve Qwen/Qwen2.5-VL-3B-Instruct \
  --host 127.0.0.1 \
  --port 8001 \
  --api-key local-token \
  --dtype auto \
  --max-model-len 8192 \
  --limit-mm-per-prompt image=1 \
  --generation-config vllm
```

If your GPU has more memory, `Qwen/Qwen2.5-VL-7B-Instruct` should usually read forms better. If the Qwen model is not available in your vLLM version, use a supported vision model from the vLLM supported-models docs.

Smoke test the local server:

```bash
curl http://127.0.0.1:8001/v1/models \
  -H "Authorization: Bearer local-token"
```

If the parser runs on Windows and vLLM runs inside WSL2, `127.0.0.1` usually forwards correctly. If it does not, get the WSL IP with `hostname -I` inside WSL and set `LOCAL_VLLM_BASE_URL=http://<wsl-ip>:8001/v1`.

### 2. Configure This App

Copy `.env.example` to `.env`, then set:

```env
VLM_PROVIDER=local_vllm
LOCAL_VLLM_BASE_URL=http://127.0.0.1:8001/v1
LOCAL_VLLM_API_KEY=local-token
LOCAL_VLLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct
LOCAL_VLLM_TEMPERATURE=0
API_ENABLE_VLM=true
```

`OPENAI_API_KEY` is not required for local VLM parsing. It is still required if you want OpenAI embeddings during Supabase sync/search.

### 3. Start The Parser

```powershell
# API
cd apps/api
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Web, in another terminal
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000`.

### 4. Test Local VLM Extraction

1. Upload a PDF.
2. Click `Parse`.
3. Low-confidence pages route through `local_vllm` automatically.
4. To force one page through local vLLM, set the page number and click `Re-run page with VLM`.
5. To force all pages through VLM during testing, set:

```env
API_LOW_CONFIDENCE_THRESHOLD=1
```

The page debug cards show the route used per page. A successful local VLM page should show `local_vllm`.

### Troubleshooting

- `Configured VLM provider is not available`: check `VLM_PROVIDER`, `LOCAL_VLLM_BASE_URL`, and `LOCAL_VLLM_MODEL`.
- Connection refused: confirm vLLM is still running and the parser can reach `http://127.0.0.1:8001/v1/models`.
- CUDA out of memory: use a smaller VLM, reduce `--max-model-len`, or reduce concurrent parsing.
- JSON schema errors from vLLM: try a newer vLLM version or a different vision model. Local models are less reliable than GPT-5.5 for strict JSON extraction, so the parser stores the raw VLM response in the page debug artifact.
- Weak OCR/form reading: try a stronger vision model such as a 7B+ VLM, or rely on local OCR plus manual JSON correction for early tests.
