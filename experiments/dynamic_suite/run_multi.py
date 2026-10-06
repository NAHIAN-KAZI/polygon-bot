"""Multi-turn live suite: a model plays a customer who holds a long conversation and
may say anything at any point -- interrupt a pending question, change their mind, go
back to an earlier topic, answer vaguely, ask what an answer means, switch intent.

  python -m experiments.dynamic_suite.run_multi [--conversations 6] [--turns 12] [--seed 1]

Each conversation is built from a random mix of status-doc rows across different
intents (the customer's goals). The customer never confirms a change, never sends a
code, PIN or password (they are told to say no or move on). Judging per turn: the
route when the turn pursues a known goal, automatic reply checks, repeated replies,
and a model verdict "did the reply respond to what they said". The model verdict is
weak (8B) -- it flags, a human reads. Report: experiments/results/dynamic/multi_<time>.md
"""
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

import httpx

os.environ.setdefault("EVAL_API_KEY", os.environ.get("API_KEY", ""))
from app.config import settings  # noqa: E402
from experiments.dynamic_suite.checks import judge, reply_flags  # noqa: E402
from experiments.live_freeze_test import chat, login  # noqa: E402

QUESTIONS = Path(__file__).with_name("questions.json")
OUT = Path(__file__).resolve().parents[1] / "results" / "dynamic"

TONES = ["terse and impatient, short messages", "chatty and friendly", "formal and careful",
         "casual, lowercase, some typos",
         "anxious, worried about their money", "vague, doesn't say exactly what they want"]
BEHAVIOURS = [
    ("pursue", "Move on to your next goal in your own words."),
    ("pursue", "Move on to your next goal, but say it in just one or two words."),
    ("pursue", "Move on to your next goal and wrap it in a long, rambling paragraph with some backstory."),
    ("answer", "Answer the assistant's last question briefly. If it asked nothing, ask a short follow-up about its last answer."),
    ("answer", "Answer the assistant's last question only partly or vaguely."),
    ("interrupt", "Interrupt whatever is going on with a completely different banking question of your own choosing."),
    ("explain", "Ask the assistant to explain what its last answer means for you, in plain words."),
    ("change", "Change your mind about what you just asked for, or correct something you said."),
    ("back", "Go back to something you asked about earlier in this conversation."),
    ("chat", "Say something casual or off-topic (thanks, a joke, a question that isn't about banking)."),
]


async def llm(messages, *, json_mode=True, temperature=0.8) -> dict | str:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={"model": settings.OLLAMA_MODEL, "messages": messages, "stream": False,
                  "think": settings.OLLAMA_THINK, **({"format": "json"} if json_mode else {}),
                  "options": {"num_ctx": settings.OLLAMA_NUM_CTX, "temperature": temperature, "num_predict": 300}},
        )
        resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return json.loads(content) if json_mode else content


def transcript_text(turns: list[dict]) -> str:
    return "\n".join(f"Customer: {t['customer']}\nAssistant: {t['bot']}" for t in turns) or "(nothing said yet)"


async def next_customer_message(tone, goals, done, turns, behaviour_text) -> str:
    prompt = (
        f"You are playing a customer of a Bangladeshi bank, writing in English, chatting with the bank's assistant in its app. "
        f"Your manner: {tone}.\n"
        f"Things you want to get done in this chat, in no fixed order: {'; '.join(goals)}.\n"
        f"Already covered: {'; '.join(done) or 'nothing yet'}.\n\n"
        f"Conversation so far:\n{transcript_text(turns)}\n\n"
        f"Now: {behaviour_text}\n"
        "Rules: write only what the customer types. Never type a PIN, password or one-time code. "
        "If the assistant asks you to confirm a change, say no or move on. Keep it natural.\n"
        'Reply with JSON: {"message": "<what the customer types>"}'
    )
    got = await llm([{"role": "user", "content": prompt}])
    return str(got.get("message") or "").strip() or "hello"


async def verdict(customer: str, bot: str) -> dict:
    prompt = (
        "A bank customer wrote a message and the bank's assistant replied. Judge ONLY whether the reply "
        "responds to what the customer asked or said (answering it, asking a sensible question about it, or "
        "politely saying it can't be done here).\n"
        f"Customer: {customer}\nAssistant: {bot}\n"
        'Reply with JSON: {"verdict": "good" or "off", "reason": "<one short sentence>"}'
    )
    try:
        return await llm([{"role": "user", "content": prompt}], temperature=0)
    except Exception:
        return {"verdict": "unknown", "reason": "judge failed"}


async def conversation(client, state, rows, rng, n_turns, idx) -> dict:
    keys = rng.sample(list(rows), 12)
    picked, seen = [], set()
    for k in keys:  # goals from different intents
        if rows[k]["intent"] not in seen and rows[k]["expected"] != "KB":
            picked.append(k)
            seen.add(rows[k]["intent"])
        if len(picked) == 5:
            break
    goals = [rows[k]["name"].split(" ", 1)[-1] if rows[k]["name"][0].isdigit() else rows[k]["name"].lstrip("— ")
             for k in picked]
    tone = rng.choice(TONES)
    turns, done, goal_i = [], [], 0
    for t in range(n_turns):
        kind, behaviour = rng.choice(BEHAVIOURS) if t else BEHAVIOURS[0]
        if kind == "pursue" and goal_i >= len(picked):
            kind, behaviour = "back", BEHAVIOURS[8][1]
        text = behaviour
        target = None
        if kind == "pursue":
            target = picked[goal_i]
            text = (f"{behaviour} The goal is: {goals[goal_i]}. Say it as a real customer would, "
                    "without technical words.")
        message = await next_customer_message(tone, goals,
                                              done, turns, text)
        start = time.monotonic()
        reply, result = await chat(client, state["token"], message)
        if result.get("type") == "AUTH_REQUIRED":
            state["token"] = await login(client)
            reply, result = await chat(client, state["token"], message)
        secs = time.monotonic() - start
        status, why = ("", "")
        if target:
            exp = rows[target]["expected"]
            status, why = judge(tuple(exp) if isinstance(exp, list) else exp, reply, result)
            done.append(goals[goal_i])
            goal_i += 1
        flags = reply_flags(reply, result.get("type") or "")
        if turns and reply == turns[-1]["bot"]:
            flags.append("repeats_previous_reply")
        v = await verdict(message, reply)
        turns.append({"n": t + 1, "behaviour": kind, "target": target, "customer": message, "bot": reply,
                      "type": result.get("type"),
                      "route": f'{result.get("category")}/{result.get("service")}/{result.get("subservice")}',
                      "route_status": status, "route_why": why, "flags": flags,
                      "verdict": v.get("verdict"), "verdict_reason": v.get("reason"), "secs": round(secs, 1)})
        print(f"[{idx}.{t+1:02}] {kind:9} {status or '-':11} {v.get('verdict')!s:5} {flags or ''} "
              f"C: {message[:70]!r} B: {reply[:80]!r}", flush=True)
    return {"id": idx, "tone": tone, "goals": goals, "turns": turns}


def report(convs: list[dict], path: Path) -> None:
    all_turns = [t for c in convs for t in c["turns"]]
    bad = [t for t in all_turns if t["verdict"] == "off" or t["flags"] or t["route_status"] in ("FAIL", "ERROR")]
    lines = [f"# Multi-turn live suite — {len(convs)} conversations, {len(all_turns)} turns", "",
             f"Turns flagged (route fail / checks / judge says off): {len(bad)}", ""]
    for c in convs:
        lines += [f"## Conversation {c['id']} — {c['tone']}", f"Goals: {'; '.join(c['goals'])}", ""]
        for t in c["turns"]:
            mark = " ⚠" if t in bad else ""
            lines += [f"**{t['n']}. [{t['behaviour']}]**{mark} Customer: {t['customer']}",
                      f"   Bot: {t['bot']}",
                      f"   `{t['type']} {t['route']}` route={t['route_status'] or '-'} {t['route_why']} "
                      f"judge={t['verdict']} ({t['verdict_reason']}) flags={t['flags']}", ""]
    path.write_text("\n".join(lines))
    print(f"\nreport: {path}  flagged {len(bad)}/{len(all_turns)}")


async def main():
    arg = lambda name, default: type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default
    n_conv, n_turns, seed = arg("--conversations", 6), arg("--turns", 12), arg("--seed", 1)
    rows = json.loads(QUESTIONS.read_text())
    rng = random.Random(seed)
    OUT.mkdir(parents=True, exist_ok=True)
    convs = []
    async with httpx.AsyncClient(timeout=60) as client:
        state = {"token": await login(client)}
        for i in range(1, n_conv + 1):
            convs.append(await conversation(client, state, rows, rng, n_turns, i))
            await chat(client, state["token"], "ok thanks, that's all")
    report(convs, OUT / f"multi_{time.strftime('%Y%m%d_%H%M%S')}.md")


if __name__ == "__main__":
    asyncio.run(main())
