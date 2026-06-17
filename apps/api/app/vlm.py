import base64
import json
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .models import DocumentDraft, ExtractedField, ExtractedTable, VlmModelInfo, WarningItem
from .normalization import normalize_value


VLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "value_raw": {"type": ["string", "null"]},
                    "value_normalized": {"type": ["string", "null"]},
                    "type": {"type": "string"},
                    "section": {"type": ["string", "null"]},
                    "page": {"type": "integer"},
                    "confidence": {"type": "number"},
                    "bbox": {
                        "type": ["array", "null"],
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "evidence": {"type": ["string", "null"]},
                },
                "required": [
                    "label",
                    "value_raw",
                    "value_normalized",
                    "type",
                    "section",
                    "page",
                    "confidence",
                    "bbox",
                    "evidence",
                ],
            },
        },
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": ["string", "null"]},
                    "page": {"type": "integer"},
                    "rows": {"type": "array", "items": {"type": "object"}},
                    "confidence": {"type": "number"},
                },
                "required": ["title", "page", "rows", "confidence"],
            },
        },
        "warnings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "severity": {"type": "string"},
                },
                "required": ["code", "message", "page", "severity"],
            },
        },
    },
    "required": ["fields", "tables", "warnings"],
}


def _image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _output_text(response: Any) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text
    output = getattr(response, "output", None) or []
    chunks: list[str] = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _draft_from_payload(payload: dict[str, Any], page_number: int) -> DocumentDraft:
    fields: list[ExtractedField] = []
    for item in payload.get("fields", []):
        label = item.get("label") or "Unknown"
        raw_value = item.get("value_raw")
        value_type, normalized = normalize_value(label, raw_value)
        fields.append(
            ExtractedField(
                label=label,
                value_raw=raw_value,
                value_normalized=item.get("value_normalized") or normalized,
                type=item.get("type") or value_type,
                section=item.get("section"),
                page=page_number,
                confidence=max(0.0, min(1.0, float(item.get("confidence") or 0.0))),
                bbox=item.get("bbox"),
                evidence=item.get("evidence"),
                source="vlm",
            )
        )

    tables = [
        ExtractedTable(
            title=item.get("title"),
            page=page_number,
            rows=item.get("rows") or [],
            confidence=max(0.0, min(1.0, float(item.get("confidence") or 0.0))),
            source="vlm",
        )
        for item in payload.get("tables", [])
    ]
    warnings = [WarningItem(**item) for item in payload.get("warnings", [])]
    return DocumentDraft(
        document_id="vlm-page",
        fields=fields,
        tables=tables,
        warnings=warnings,
    )


def _extract_page_with_openai_responses(
    *,
    image_path: Path,
    page_number: int,
    api_key: str,
    model: str,
) -> tuple[DocumentDraft, dict[str, Any]]:
    from openai import OpenAI

    prompt = (
        "Extract visible key-value pairs and table-like cost rows from this German "
        "infrastructure planning approval page. Preserve original German labels exactly "
        "when legible. Return only fields that are visible. Use null for unknown values. "
        "Use page number "
        f"{page_number}. Include short evidence snippets and confidence per item."
    )
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": _image_data_url(image_path),
                        "detail": "high",
                    },
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "pdf_page_key_values",
                "schema": VLM_SCHEMA,
                "strict": True,
            }
        },
    )
    raw_text = _output_text(response)
    payload = json.loads(raw_text)
    return _draft_from_payload(payload, page_number), {"raw_response": raw_text, "model": model}


def _extract_page_with_local_vllm(
    *,
    image_path: Path,
    page_number: int,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
) -> tuple[DocumentDraft, dict[str, Any]]:
    from openai import OpenAI

    prompt = (
        "You are extracting data from a German infrastructure planning approval PDF page. "
        "Read the image and return JSON only. Extract visible key-value pairs and table-like "
        "cost rows. Preserve original German labels exactly when legible. Use null for unknown "
        f"values. Use page number {page_number}. Include evidence snippets and confidence per item."
    )
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_data_url(image_path)},
                    },
                ],
            }
        ],
        temperature=temperature,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "pdf_page_key_values",
                "schema": VLM_SCHEMA,
            },
        },
    )
    raw_text = response.choices[0].message.content or "{}"
    payload = json.loads(raw_text)
    return _draft_from_payload(payload, page_number), {
        "raw_response": raw_text,
        "model": model,
        "base_url": base_url,
    }


def _extract_page_with_ollama(
    *,
    image_path: Path,
    page_number: int,
    base_url: str,
    model: str,
    temperature: float,
) -> tuple[DocumentDraft, dict[str, Any]]:
    prompt = (
        "You are extracting data from a German infrastructure planning approval PDF page. "
        "Read the image and return JSON only. Extract visible key-value pairs and table-like "
        "cost rows. Preserve original German labels exactly when legible. Use null for unknown "
        f"values. Use page number {page_number}. Include evidence snippets and confidence per item. "
        f"JSON schema: {json.dumps(VLM_SCHEMA, ensure_ascii=False)}"
    )
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
            }
        ],
        "stream": False,
        "format": VLM_SCHEMA,
        "options": {"temperature": temperature},
    }
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/chat",
        json=request_payload,
        timeout=180,
    )
    response.raise_for_status()
    response_payload = response.json()
    raw_text = (response_payload.get("message") or {}).get("content") or "{}"
    payload = json.loads(raw_text)
    return _draft_from_payload(payload, page_number), {
        "raw_response": raw_text,
        "model": model,
        "base_url": base_url,
    }


def extract_page_with_vlm(
    *,
    image_path: Path,
    page_number: int,
    settings: Settings,
) -> tuple[DocumentDraft, dict[str, Any]]:
    if settings.vlm_provider == "local_vllm":
        return _extract_page_with_local_vllm(
            image_path=image_path,
            page_number=page_number,
            base_url=settings.local_vllm_base_url,
            api_key=settings.local_vllm_api_key,
            model=settings.local_vllm_model,
            temperature=settings.local_vllm_temperature,
        )
    if settings.vlm_provider == "ollama":
        return _extract_page_with_ollama(
            image_path=image_path,
            page_number=page_number,
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=settings.ollama_temperature,
        )
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required when VLM_PROVIDER=openai")
    return _extract_page_with_openai_responses(
        image_path=image_path,
        page_number=page_number,
        api_key=settings.openai_api_key,
        model=settings.openai_vision_model,
    )


VISION_MODEL_NAME_HINTS = (
    "vision",
    "vl",
    "llava",
    "bakllava",
    "moondream",
    "minicpm-v",
    "minicpmv",
    "qwen2.5vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "gemma3",
    "gemma4",
    "pixtral",
    "granite-vision",
    "glm-ocr",
    "deepseek-ocr",
    "mistral-small",
)


def _is_likely_vision_model(model_id: str, details: dict[str, Any] | None = None) -> bool:
    text = model_id.lower()
    if any(hint in text for hint in VISION_MODEL_NAME_HINTS):
        return True
    details = details or {}
    families = details.get("families") or []
    family_text = " ".join(str(item).lower() for item in families)
    return any(hint in family_text for hint in VISION_MODEL_NAME_HINTS)


def list_vlm_models(settings: Settings, provider: str | None = None) -> tuple[list[VlmModelInfo], str]:
    selected_provider = provider or settings.vlm_provider
    if selected_provider == "ollama":
        try:
            response = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=5)
            response.raise_for_status()
        except Exception as exc:
            return [], f"Ollama model listing failed: {exc}"
        models = []
        for item in response.json().get("models", []):
            model_id = item.get("model") or item.get("name")
            if not model_id:
                continue
            details = item.get("details") or {}
            models.append(
                VlmModelInfo(
                    id=model_id,
                    provider="ollama",
                    vision_likely=_is_likely_vision_model(model_id, details),
                    details=item,
                )
            )
        return models, f"{len(models)} Ollama model(s) installed"

    if selected_provider == "local_vllm":
        try:
            response = httpx.get(
                f"{settings.local_vllm_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {settings.local_vllm_api_key}"},
                timeout=5,
            )
            response.raise_for_status()
        except Exception as exc:
            fallback = VlmModelInfo(
                id=settings.local_vllm_model,
                provider="local_vllm",
                installed=False,
                vision_likely=_is_likely_vision_model(settings.local_vllm_model),
            )
            return [fallback], f"vLLM model listing failed; showing configured model: {exc}"
        models = [
            VlmModelInfo(
                id=item["id"],
                provider="local_vllm",
                vision_likely=_is_likely_vision_model(item["id"]),
                details=item,
            )
            for item in response.json().get("data", [])
            if item.get("id")
        ]
        return models, f"{len(models)} vLLM model(s) available"

    configured = settings.openai_vision_model
    return [
        VlmModelInfo(
            id=configured,
            provider="openai",
            installed=bool(settings.openai_api_key),
            vision_likely=True,
        )
    ], "Hosted OpenAI model from configuration"
