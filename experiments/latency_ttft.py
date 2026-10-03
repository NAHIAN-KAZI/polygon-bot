"""Time to first token and total time per turn against the running /chat server.
Run inside the backend container with EVAL_API_KEY, EVAL_USERNAME, EVAL_PASSWORD set:
  python -m experiments.latency_ttft"""
import os
import time

import httpx

MESSAGES = ["balance", "show my last transactions", "whats my transfer limit",
            "send 1500 taka to my bkash 01711223344", "i lost my card", "what is a savings account"]


def main():
    login = httpx.post("https://internet-banking.dev-polygontech.xyz/auth/v1/auth/login",
                       json={"username": os.environ["EVAL_USERNAME"], "password": os.environ["EVAL_PASSWORD"]},
                       headers={"User-Agent": "curl/8.5.0"}, timeout=30)
    token = login.json()["token"]["accessToken"]
    headers = {"X-API-Key": os.environ["EVAL_API_KEY"], "Authorization": f"Bearer {token}"}
    for msg in MESSAGES:
        started, first = time.monotonic(), None
        with httpx.stream("POST", "http://localhost:8000/chat", json={"message": msg},
                          headers=headers, timeout=180) as resp:
            for line in resp.iter_lines():
                if first is None and line.startswith("event: token"):
                    first = time.monotonic() - started
        total = time.monotonic() - started
        print(f"{msg!r:45} first text {first:5.1f}s   total {total:5.1f}s")


if __name__ == "__main__":
    main()
