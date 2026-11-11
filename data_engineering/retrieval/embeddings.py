"""Embedding model wrapper. Owner: Person A. (Tests replace _get() with a fake model.)"""
from functools import lru_cache
from data_engineering import config


@lru_cache(maxsize=1)
def _get():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.params()["embedding"]["model"])


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _get().encode(texts, normalize_embeddings=True, batch_size=64).tolist()


def _prefix() -> str:
    return config.params()["embedding"].get("query_prefix", "")


def embed_query(question: str) -> list[float]:
    return _get().encode([_prefix() + question], normalize_embeddings=True).tolist()[0]
