"""Offline retrieval evaluation for the knowledge file (T-123).

Chunks a knowledge file exactly as `POST /documents` does, embeds the chunks with the bot's own embedding code
(cached on disk, so a re-run is fast), and ranks them by cosine similarity in memory. No Qdrant, no chat model.
A strategy is a function (question) -> chunk indexes, best first; the baseline is what production does today
(embed the message, rank every chunk).

A question counts as answered at rank r when the r-th chunk matches one of its `expect` groups. A group is a list of
lowercase substrings that must all appear in the chunk's heading path (group > product > section). These oracles
live in the question sets only; the bot itself never sees them.
"""
import hashlib
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).parent / ".cache"


@dataclass(frozen=True)
class Question:
    text: str
    expect: tuple[tuple[str, ...], ...]  # any one group may match; a group needs all its substrings
    kind: str = "generic"


def heading_text(chunk) -> str:
    return " > ".join(chunk.heading_path).lower()


def matches(chunk, question: Question) -> bool:
    path = heading_text(chunk)
    return any(all(part in path for part in group) for group in question.expect)


def faq_questions(chunks) -> list[Question]:
    """One question per distinct FAQ-style heading (ends with '?'); any chunk carrying that heading answers it."""
    seen, out = set(), []
    for chunk in chunks:
        if not chunk.heading_path:
            continue
        title = chunk.heading_path[-1].strip()
        if not title.endswith("?") or len(title.split()) < 3 or title.lower() in seen:
            continue  # "Want more details?" is a page footer, not a question
        seen.add(title.lower())
        out.append(Question(title, ((re.sub(r"\s+", " ", title.lower()),),), "faq"))
    return out


def load_generic(path: Path) -> list[Question]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [Question(r["q"], tuple(tuple(p.lower() for p in group) for group in r["expect"]), "generic") for r in rows]


def rank_of_first_match(order, chunks, question: Question) -> int | None:
    """1-based rank of the first chunk in `order` that answers the question, or None."""
    for position, index in enumerate(order, start=1):
        if matches(chunks[index], question):
            return position
    return None


def summarise(ranks: list[int | None]) -> dict:
    found = [r for r in ranks if r is not None]
    n = len(ranks) or 1
    return {
        "questions": len(ranks),
        "recall@1": sum(1 for r in found if r <= 1) / n,
        "recall@5": sum(1 for r in found if r <= 5) / n,
        "recall@10": sum(1 for r in found if r <= 10) / n,
        "recall@20": sum(1 for r in found if r <= 20) / n,
        "recall@30": sum(1 for r in found if r <= 30) / n,
        "mrr": sum(1 / r for r in found) / n,
        "median_rank": statistics.median(found) if found else None,
        "not_found": len(ranks) - len(found),
    }


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """texts -> vectors for one embedding model, stored under experiments/kb_eval/.cache (git-ignored)."""

    def __init__(self, model: str):
        self.path = CACHE_DIR / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', model)}.json"
        self.vectors: dict[str, list[float]] = json.loads(self.path.read_text()) if self.path.exists() else {}

    async def embed(self, texts: list[str], embed_texts) -> np.ndarray:
        missing = list(dict.fromkeys(t for t in texts if _key(t) not in self.vectors))
        if missing:
            for key, vector in zip((_key(t) for t in missing), await embed_texts(missing)):
                self.vectors[key] = vector
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.vectors))
        matrix = np.array([self.vectors[_key(t)] for t in texts], dtype=np.float32)
        return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-9)


def cosine_order(query_vector: np.ndarray, matrix: np.ndarray) -> list[int]:
    return list(np.argsort(-(matrix @ query_vector)))
