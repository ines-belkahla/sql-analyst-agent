"""Rerank the tables found by Qdrant with a cross-encoder.

Why: Qdrant compares the question and each table separately (bi-encoder: fast, rough).
A cross-encoder reads the question AND the table text together (slower, more precise),
so we use it only on the few candidates Qdrant returns.

Used through data_api.search_schema(question, db_id, rerank=True).
"""
from functools import lru_cache

from data_engineering.config import RERANK_MODEL


@lru_cache(maxsize=1)
def get_reranker():
    from sentence_transformers import CrossEncoder  # imported here: heavy, only needed for reranking

    # max_length=512: longer table documents are truncated by the model
    return CrossEncoder(RERANK_MODEL, max_length=512)


def rerank_hits(question, hits, top_n=3):
    """hits: list of dicts with a 'text' key (as returned by search_schema).
    Returns the top_n hits sorted by reranker score; 'score' is replaced by that score."""
    if not hits:
        return hits
    scores = get_reranker().predict([(question, h["text"]) for h in hits])
    ranked = sorted(zip(hits, scores), key=lambda pair: pair[1], reverse=True)
    return [{**h, "score": round(float(s), 4)} for h, s in ranked[:top_n]]
