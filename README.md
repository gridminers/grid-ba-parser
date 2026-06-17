# grid-ba-parser

Technical workbench for extracting flexible key-value data from unstructured German infrastructure approval PDFs.

The project contains:

- `apps/api` - FastAPI ingestion, PDF rendering, OCR, hybrid VLM extraction, validation, and Supabase sync.
- `apps/web` - Minimal technical operator console for upload, parse jobs, JSON editing, debug artifacts, and sync.
- `supabase/schema.sql` - Postgres/Supabase schema, including pgvector tables for approved chunks.
- `docs/parser-prototype-plan.md` - Architecture and implementation plan.

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

## Runtime Notes

- Local PDF text extraction and rendering use PyMuPDF.
- OCR uses `pytesseract` if the Tesseract binary is installed locally; otherwise pages can still fall back to VLM.
- Hosted OpenAI VLM extraction is enabled when `VLM_PROVIDER=openai` and `OPENAI_API_KEY` are configured.
- Local vLLM extraction is enabled when `VLM_PROVIDER=local_vllm` and a vLLM OpenAI-compatible server is running.
- Local Ollama extraction is enabled when `VLM_PROVIDER=ollama` and Ollama is running on your machine.
- Supabase sync is enabled when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are configured.
- Approved embeddings use `text-embedding-3-small` by default and are stored in Supabase/Postgres via pgvector.

This is intentionally not a polished analytics app. It is a technical extraction console for operators comfortable with raw JSON and unstructured data.

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
