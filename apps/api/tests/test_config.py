from app.config import Settings


def test_local_vllm_provider_does_not_require_openai_key(tmp_path):
    settings = Settings(
        API_DATA_DIR=tmp_path,
        VLM_PROVIDER="local_vllm",
        LOCAL_VLLM_BASE_URL="http://127.0.0.1:8001/v1",
        LOCAL_VLLM_MODEL="test-vlm",
    )

    assert settings.vlm_available is True


def test_ollama_provider_does_not_require_openai_key(tmp_path):
    settings = Settings(
        API_DATA_DIR=tmp_path,
        VLM_PROVIDER="ollama",
        OLLAMA_BASE_URL="http://127.0.0.1:11434",
        OLLAMA_MODEL="qwen2.5vl",
        OPENAI_API_KEY=None,
    )

    assert settings.vlm_available is True


def test_openai_provider_requires_openai_key(tmp_path):
    settings = Settings(API_DATA_DIR=tmp_path, VLM_PROVIDER="openai", OPENAI_API_KEY=None)

    assert settings.vlm_available is False
