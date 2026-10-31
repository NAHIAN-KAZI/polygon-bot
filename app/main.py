import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.banking.taxonomy import initialize_taxonomy
from app.config import settings
from app.llm import check_ollama
from app import catalog
from app.knowledge import live_rates
from app.vectorstore import check_qdrant, ensure_collection
from app.routes import documents, chat, demo_login, tts

logging.basicConfig(level=logging.INFO, format="%(message)s")

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
    catalog.fail_interrupted()   # a document still "indexing" lost its background task with the last process
    await initialize_taxonomy()
    if settings.RATES_WARM:
        app.state.rates_warm = asyncio.create_task(live_rates.keep_warm())


@app.get("/health")
async def health():
    ollama_ok = await check_ollama()
    qdrant_ok = check_qdrant()
    status = "ok" if (ollama_ok and qdrant_ok) else "degraded"
    return {"status": status, "ollama": ollama_ok, "qdrant": qdrant_ok}


app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(demo_login.router)
app.include_router(demo_login.config_router)
app.include_router(tts.router)

class _RevalidatingStaticFiles(StaticFiles):
    """The demo frontend is three files that change together; without a cache header a browser
    kept an old app.js against a new index.html. no-cache = always revalidate (cheap 304s)."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", _RevalidatingStaticFiles(directory="frontend", html=True), name="frontend")
