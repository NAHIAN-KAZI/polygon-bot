from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.banking.taxonomy import initialize_taxonomy
from app.config import settings
from app.llm import check_ollama
from app.vectorstore import check_qdrant, ensure_collection
from app.routes import documents, chat

app = FastAPI(title="RAG Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    ensure_collection()
    await initialize_taxonomy()


@app.get("/health")
async def health():
    ollama_ok = await check_ollama()
    qdrant_ok = check_qdrant()
    status = "ok" if (ollama_ok and qdrant_ok) else "degraded"
    return {"status": status, "ollama": ollama_ok, "qdrant": qdrant_ok}


app.include_router(documents.router)
app.include_router(chat.router)

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
