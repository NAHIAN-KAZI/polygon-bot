"""Per-call LLM timing inside real /chat turns. Run inside the backend container:
  python -m experiments.latency_probe
Wraps httpx.AsyncClient.post to record every Ollama call's wall time and Ollama's own
prompt-eval / generation counters, then drives the real /chat route in-process."""
import asyncio
import json
import os
import time

import httpx

calls = []
_orig = httpx.AsyncClient.post


async def timed_post(self, url, *args, **kwargs):
    started = time.monotonic()
    resp = await _orig(self, url, *args, **kwargs)
    if "11434" in str(url):
        try:
            body = resp.json()
        except Exception:
            body = {}
        calls.append({
            "api": str(url).rsplit("/", 1)[-1],
            "wall": round(time.monotonic() - started, 2),
            "prompt_tok": body.get("prompt_eval_count"),
            "prompt_s": round((body.get("prompt_eval_duration") or 0) / 1e9, 2),
            "gen_tok": body.get("eval_count"),
            "gen_s": round((body.get("eval_duration") or 0) / 1e9, 2),
            "load_s": round((body.get("load_duration") or 0) / 1e9, 2),
        })
    return resp

httpx.AsyncClient.post = timed_post

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

MESSAGES = ["balance", "show my last transactions", "whats my transfer limit",
            "send 1500 taka to my bkash 01711223344", "i lost my card", "what is a savings account"]


def main():
    login = httpx.post("https://internet-banking.dev-polygontech.xyz/auth/v1/auth/login",
                       json={"username": os.environ["EVAL_USERNAME"], "password": os.environ["EVAL_PASSWORD"]},
                       headers={"User-Agent": "curl/8.5.0"}, timeout=30)
    token = login.json()["token"]["accessToken"]
    with TestClient(app) as client:
        for msg in MESSAGES:
            calls.clear()
            started = time.monotonic()
            client.post("/chat", json={"message": msg},
                        headers={"X-API-Key": os.environ["EVAL_API_KEY"], "Authorization": f"Bearer {token}"})
            total = time.monotonic() - started
            llm = sum(c["wall"] for c in calls)
            print(f"\n{msg!r}: total {total:.1f}s, LLM {llm:.1f}s in {len(calls)} calls, other {total - llm:.1f}s")
            for c in calls:
                print("   ", json.dumps(c))


if __name__ == "__main__":
    main()
