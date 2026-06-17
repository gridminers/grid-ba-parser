# Local VLM Setup On Ubuntu/WSL2

This project is developed from Windows at `C:\Projects\grid-ba-parser`, but vLLM should be run from Ubuntu/WSL2. Native Windows vLLM installs are unreliable because vLLM primarily targets Linux CUDA/PyTorch environments.

Use Ollama on Windows for the fastest no-key test. Use Ubuntu/WSL2 when you specifically want a local vLLM OpenAI-compatible server.

## Recommended Local Topology

- Windows runs the FastAPI app on `http://127.0.0.1:8000`.
- Windows runs the Next.js technical console on `http://127.0.0.1:3000`.
- Ubuntu/WSL2 runs vLLM on `http://127.0.0.1:8001/v1`.
- The backend connects to vLLM through `LOCAL_VLLM_BASE_URL`.

Use port `8001` for vLLM because the FastAPI app already owns port `8000`.

## Install Ubuntu/WSL2

Run in Windows PowerShell:

```powershell
wsl --install -d Ubuntu
```

Restart Windows if prompted, then open the Ubuntu terminal.

## Install And Serve vLLM

Run inside Ubuntu:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip

python3 -m venv .venv-vllm
source .venv-vllm/bin/activate
pip install --upgrade pip
pip install vllm
```

Serve a small vision model:

```bash
vllm serve Qwen/Qwen2.5-VL-3B-Instruct \
  --host 0.0.0.0 \
  --port 8001 \
  --api-key local-token \
  --dtype auto \
  --max-model-len 8192 \
  --limit-mm-per-prompt image=1 \
  --generation-config vllm
```

Smoke test from Ubuntu:

```bash
curl http://127.0.0.1:8001/v1/models \
  -H "Authorization: Bearer local-token"
```

Smoke test from Windows PowerShell:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/v1/models `
  -Headers @{ Authorization = "Bearer local-token" }
```

## Project `.env` For vLLM

Set this in the project `.env` on Windows:

```env
VLM_PROVIDER=local_vllm
LOCAL_VLLM_BASE_URL=http://127.0.0.1:8001/v1
LOCAL_VLLM_API_KEY=local-token
LOCAL_VLLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct
LOCAL_VLLM_TEMPERATURE=0
API_ENABLE_VLM=true
```

Restart the FastAPI backend after changing `.env`.

In the UI:

1. Select `vLLM local`.
2. Click `Refresh models`.
3. Select `Qwen/Qwen2.5-VL-3B-Instruct`.
4. Upload a PDF.
5. Click `Parse`, or force a page through vLLM with `Re-run page with VLM`.

## WSL Networking Notes

Usually Windows can reach WSL services through `127.0.0.1`. If it cannot, run this inside Ubuntu:

```bash
hostname -I
```

Then set:

```env
LOCAL_VLLM_BASE_URL=http://<wsl-ip>:8001/v1
```

## GPU Notes

vLLM is practical only with a compatible GPU. If installation or serving fails because of CUDA, PyTorch, or memory issues:

- Confirm NVIDIA drivers and WSL GPU support are installed.
- Try a smaller model.
- Reduce `--max-model-len`.
- Use Ollama for the first parser test if vLLM setup blocks progress.

## When To Use Ollama Instead

Use Ollama if you only need to see whether the parser can send rendered PDF pages to a local vision model and receive editable JSON. It is simpler on Windows and does not require the vLLM OpenAI-compatible server.
