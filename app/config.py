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
    # How tool calls reach an OpenAI-compatible server: "emulated" (forced JSON, works on any
    # server), "native_auto" or "native_required" (needs vLLM --enable-auto-tool-choice).
    LLM_TOOL_MODE: str = os.environ.get("LLM_TOOL_MODE", "emulated")
    # Context size shown in usage stats; 0 = ask the server (max_model_len) or use OLLAMA_NUM_CTX.
    LLM_CONTEXT_WINDOW: int = int(os.environ.get("LLM_CONTEXT_WINDOW", "0"))
    # Whether the text-generation model reads images (chat requests may then attach one).
    LLM_IMAGE_INPUT: bool = os.environ.get("LLM_IMAGE_INPUT", "false").lower() == "true"
    MAX_IMAGE_MB: int = int(os.environ.get("MAX_IMAGE_MB", "5"))
    # Whether the model hears audio (gemma4 on vLLM does; Ollama never). Voice messages are
    # then transcribed by the model and answered like typed text.
    LLM_AUDIO_INPUT: bool = os.environ.get("LLM_AUDIO_INPUT", "false").lower() == "true"
    # Gemma 4 hears at most 30 s per clip; vLLM silently drops the rest (a 67 s test clip lost
    # its last sentence, no error), so longer messages are refused instead of half-heard.
    MAX_AUDIO_SECONDS: int = int(os.environ.get("MAX_AUDIO_SECONDS", "30"))
    # Separate speech-to-text server for the "nemo" voice mode (stt_service/, hishab's
    # titu_stt_bn_fastconformer on NeMo), e.g. http://spark:8791. Empty = mode not offered.
    STT_URL: str = os.environ.get("STT_URL", "").rstrip("/")
    STT_API_KEY: str = os.environ.get("STT_API_KEY", "")
    # "Read aloud" button on replies (POST /tts, Microsoft's Edge neural voices via edge-tts).
    # The reply text is sent to Microsoft and replies can hold account details, so it's off
    # unless switched on. The Bangla voice is used whenever the reply has Bangla script.
    TTS_ENABLED: bool = os.environ.get("TTS_ENABLED", "false").lower() == "true"
    TTS_VOICE_BN: str = os.environ.get("TTS_VOICE_BN", "bn-BD-NabanitaNeural")
    TTS_VOICE_EN: str = os.environ.get("TTS_VOICE_EN", "en-IN-NeerjaNeural")
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
    # Knowledge answers: the model plans the search and picks the passages that answer (app/knowledge). "false"
    # goes back to searching the message as typed.
    # Personal advice (app/advisor): how much of the customer's history is read and when a pattern counts as one.
    ADVISOR_DETAIL_MONTHS: int = int(os.environ.get("ADVISOR_DETAIL_MONTHS", "6"))       # months of transaction rows
    ADVISOR_HISTORY_MONTHS: int = int(os.environ.get("ADVISOR_HISTORY_MONTHS", "36"))    # months of monthly totals
    ADVISOR_PAGE_SIZE: int = int(os.environ.get("ADVISOR_PAGE_SIZE", "50"))
    ADVISOR_MAX_PAGES: int = int(os.environ.get("ADVISOR_MAX_PAGES", "20"))              # per account
    ADVISOR_PAYEE_CHARS: int = int(os.environ.get("ADVISOR_PAYEE_CHARS", "64"))          # longest payee text kept
    ADVISOR_CACHE_SECONDS: int = int(os.environ.get("ADVISOR_CACHE_SECONDS", "600"))
    ADVISOR_RECURRING_MIN_OCCURRENCES: int = int(os.environ.get("ADVISOR_RECURRING_MIN_OCCURRENCES", "3"))
    ADVISOR_RECURRING_INTERVAL_SPREAD: float = float(os.environ.get("ADVISOR_RECURRING_INTERVAL_SPREAD", "0.35"))
    ADVISOR_RECURRING_AMOUNT_SPREAD: float = float(os.environ.get("ADVISOR_RECURRING_AMOUNT_SPREAD", "0.2"))
    KB_QUERY_PLANNING: bool = os.environ.get("KB_QUERY_PLANNING", "true").lower() not in ("0", "false", "no")
    OLLAMA_THINK: bool = os.environ.get("OLLAMA_THINK", "false").lower() == "true"

    # Product cards (app/knowledge/product_cards.py): built from the knowledge base by the chat model.
    PRODUCT_CARDS_PATH: str = os.environ.get("PRODUCT_CARDS_PATH", "/app/data/product_cards.json")
    PRODUCT_CARD_TEXT_CHARS: int = int(os.environ.get("PRODUCT_CARD_TEXT_CHARS", "6000"))   # product text the model reads
    PRODUCT_CARD_CONCURRENCY: int = int(os.environ.get("PRODUCT_CARD_CONCURRENCY", "4"))
    DOCS_METADATA_PATH: str = os.environ.get("DOCS_METADATA_PATH", "/app/data/documents.json")

    # A document with more chunks than this is indexed in the background (the upload answers 202 at once): embedding
    # takes about 50 ms a chunk, longer than a gateway waits for a reply.
    ASYNC_UPLOAD_CHUNKS: int = int(os.environ.get("ASYNC_UPLOAD_CHUNKS", "400"))
    EMBED_BATCH: int = int(os.environ.get("EMBED_BATCH", "64"))
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
