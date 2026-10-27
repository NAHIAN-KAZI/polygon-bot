"""Finds the knowledge-base passages that answer a customer's question (T-124, T-126, T-127).

Four steps, the first and last by the model:
  1. plan     `query_plan`: standalone search queries and the products the question is about
  2. search   the customer's own words and each planned query search the whole index; reciprocal-rank fusion merges
              the lists, the customer's own words count double, and passages of the planned products get one more
              vote; the plain search's top ten always stay in the pool, so a wrong plan can only cost a boost
  3. pool     the best 30 of those
  4. rerank   `rerank`: the model keeps the passages that really answer the question, best first

`grounded` is true only when the model kept at least one passage. If the model cannot be asked (down, timeout,
unusable answer) the code falls back to the vector order and the old rule (grounded when anything matched), so the
bot never gets worse than before.
"""
import asyncio
from dataclasses import dataclass, field

from app import vectorstore
from app.config import settings
from app.embeddings import embed_texts
from app.knowledge import catalogue, query_plan, rerank

RRF_K = 60
OWN_WEIGHT = 2.0
BOOST_WEIGHT = 1.0
SEARCH_DEPTH = 60
OWN_KEPT = 10
POOL_SIZE = 30
DEFAULT_KEEP = 6
NEAREST_SHOWN = 3


@dataclass
class Retrieval:
    hits: list[dict]
    grounded: bool
    plan: query_plan.QueryPlan = field(default_factory=lambda: query_plan.QueryPlan([]))
    reranked: bool = False  # false when the model could not be asked and the vector order was used
    nearest: list[dict] = field(default_factory=list)  # related passages, when none answers the question directly


def _votes(ranked: list[list[dict]], weights: list[float], by_id: dict[str, dict]) -> dict[str, float]:
    votes: dict[str, float] = {}
    for hits, weight in zip(ranked, weights):
        for position, hit in enumerate(hits, start=1):
            by_id.setdefault(hit["id"], hit)
            votes[hit["id"]] = votes.get(hit["id"], 0.0) + weight / (RRF_K + position)
    return votes


def _fuse(own: list[dict], planned: list[list[dict]], inside: list[dict]) -> tuple[list[dict], list[dict]]:
    """(the pool of up to 30 passages, best first; the plain search's own list)."""
    by_id: dict[str, dict] = {}
    lists = [own, *planned] + ([inside] if inside else [])
    weights = [OWN_WEIGHT] + [1.0] * len(planned) + ([BOOST_WEIGHT] if inside else [])
    votes = _votes(lists, weights, by_id)
    ordered = [by_id[i] for i in sorted(votes, key=lambda i: -votes[i])]
    kept = {h["id"] for h in own[:OWN_KEPT]}
    pool = own[:OWN_KEPT] + [h for h in ordered if h["id"] not in kept]
    return pool[:POOL_SIZE], own


def _merge_best(searches: list[list[dict]]) -> list[dict]:
    """One list from several searches: each passage once, at its best score, best first."""
    best: dict[str, dict] = {}
    for hits in searches:
        for hit in hits:
            if hit["id"] not in best or hit["score"] > best[hit["id"]]["score"]:
                best[hit["id"]] = hit
    return sorted(best.values(), key=lambda h: -h["score"])


async def retrieve(message: str, recent: list[str], keep: int | None = None) -> Retrieval:
    """Raises what the embedding model or the vector store raises (the caller reports it); anything the chat model
    does wrong is absorbed by the fallbacks."""
    keep = keep or DEFAULT_KEEP
    plan = await query_plan.plan(message, recent, await asyncio.to_thread(catalogue.load))
    texts = list(dict.fromkeys([message, *plan.queries]))
    vectors = dict(zip(texts, await embed_texts(texts)))

    def search_all(products: list[str] | None) -> list[list[dict]]:
        return [vectorstore.search_in(vectors[t], SEARCH_DEPTH, products) for t in texts]

    searched = await asyncio.to_thread(search_all, None)
    inside = _merge_best(await asyncio.to_thread(search_all, plan.products)) if plan.products else []
    pool, own = _fuse(searched[0], searched[1:], inside)
    if not pool:
        return Retrieval([], False, plan, True)

    picked = await rerank.rerank(message, pool, keep)
    if picked is None:  # the model could not be asked: the plain search, as before
        floor = [h for h in own if h["score"] >= settings.MIN_RELEVANCE_SCORE][:keep]
        return Retrieval(floor, bool(floor), plan, False)
    if not picked:   # nothing answers it, but the closest passages tell the customer what the bank does have
        return Retrieval([], False, plan, True, pool[:NEAREST_SHOWN])
    return Retrieval([pool[i] for i in picked], True, plan, True)
