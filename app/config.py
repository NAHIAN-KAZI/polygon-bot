import os


class Settings:
    API_KEY: str = os.environ.get("API_KEY", "")

    OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    OLLAMA_EMBED_MODEL: str = os.environ.get("OLLAMA_EMBED_MODEL", "all-minilm")
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


settings = Settings()
