import os


class Settings:
    API_KEY: str = os.environ.get("API_KEY", "")

    OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
    OLLAMA_CLASSIFY_MODEL: str = os.environ.get("OLLAMA_CLASSIFY_MODEL", "llama3.1:8b")
    # Ollama's default context window silently truncates long prompts from the
    # start (dropping system rules), so every Ollama call sets it explicitly.
    OLLAMA_NUM_CTX: int = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
    OLLAMA_EMBED_MODEL: str = os.environ.get("OLLAMA_EMBED_MODEL", "all-minilm")

    # Text generation: "ollama" (native API at OLLAMA_BASE_URL, using the OLLAMA_* models) or
    # "openai" (any OpenAI-compatible server, e.g. vLLM; see app/llm_backend.py).
    # Embeddings always use Ollama.
    LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
    LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "").rstrip("/")  # e.g. http://host:8000/v1
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "")
    LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
    # Context size shown in usage stats; 0 = ask the server (max_model_len) or use OLLAMA_NUM_CTX.
    LLM_CONTEXT_WINDOW: int = int(os.environ.get("LLM_CONTEXT_WINDOW", "0"))
    # Whether the text-generation model reads images (chat requests may then attach one).
    LLM_IMAGE_INPUT: bool = os.environ.get("LLM_IMAGE_INPUT", "false").lower() == "true"
    MAX_IMAGE_MB: int = int(os.environ.get("MAX_IMAGE_MB", "5"))
    # Whether the model hears audio (gemma4 on vLLM does; Ollama never). Voice messages are
    # then transcribed by the model and answered like typed text.
    LLM_AUDIO_INPUT: bool = os.environ.get("LLM_AUDIO_INPUT", "false").lower() == "true"
    MAX_AUDIO_SECONDS: int = int(os.environ.get("MAX_AUDIO_SECONDS", "60"))
    EMBED_DIM: int = int(os.environ.get("EMBED_DIM", "384"))

    QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://qdrant:6333")
    QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "documents")

    # all-minilm's embedding runner caps input at 256 tokens (~3-4 chars/token for English).
    # 480 chars leaves safety margin even for denser/technical text; raise only if you
    # switch to an embedding model with a larger context window.
    CHUNK_SIZE: int = int(os.environ.get("CHUNK_SIZE", "480"))
    CHUNK_OVERLAP: int = int(os.environ.get("CHUNK_OVERLAP", "60"))

    DEFAULT_TOP_K: int = int(os.environ.get("DEFAULT_TOP_K", "5"))
    MAX_TOP_K: int = int(os.environ.get("MAX_TOP_K", "20"))
    MIN_RELEVANCE_SCORE: float = float(os.environ.get("MIN_RELEVANCE_SCORE", "0.3"))
    OLLAMA_THINK: bool = os.environ.get("OLLAMA_THINK", "false").lower() == "true"

    DOCS_METADATA_PATH: str = os.environ.get("DOCS_METADATA_PATH", "/app/data/documents.json")

    MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "25"))

    ALLOWED_ORIGINS: list[str] = [
        o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()
    ]

    PLATFORM_API_BASE_URL: str = os.environ.get("PLATFORM_API_BASE_URL", "")
    TAXONOMY_REFRESH_SECONDS: int = int(os.environ.get("TAXONOMY_REFRESH_SECONDS", "900"))

    # Dev/test convenience: a platform test account the demo portal can log in with
    # (app/routes/demo_login.py). Leave unset in production -- the endpoint then 404s.
    DEMO_LOGIN_USERNAME: str = os.environ.get("DEMO_LOGIN_USERNAME", "")
    DEMO_LOGIN_PASSWORD: str = os.environ.get("DEMO_LOGIN_PASSWORD", "")
    # Dev/test convenience: GET /demo-config gives the demo portal API_KEY so nobody has to
    # type it. Anyone who can reach the server gets the key, so keep the port local-only.
    DEMO_PORTAL_AUTOFILL_API_KEY: bool = (
        os.environ.get("DEMO_PORTAL_AUTOFILL_API_KEY", "false").lower() == "true"
    )


settings = Settings()
