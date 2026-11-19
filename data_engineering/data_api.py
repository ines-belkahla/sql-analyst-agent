"""DATA API - everything Person B needs from the data part. See DATA_API.md for examples.

    list_databases()              the 3 database names
    get_retriever(db_id, k)       LangChain retriever over one database's documents
    search_schema(question, db)   matching tables with their source (citation) and score
    get_schema_text(db_id)        the full cleaned schema as text (no RAG)
    get_table_documents(db_id)    {table (lower case): {table, text, source}} read from the documents file
    database_path(db_id)          path of the SQLite file (open it read-only)
    load_questions(split)         "dev" or "eval" questions with their reference SQL
"""
import json
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from data_engineering.config import (
    COLLECTION_NAME,
    DATABASES,
    EMBEDDING_MODEL,
    FETCH_K,
    PROCESSED_DIR,
    QDRANT_URL,
    QUESTIONS_DIR,
    TOP_K,
    database_path,
)

__all__ = ["list_databases", "get_retriever", "search_schema", "get_schema_text",
           "get_table_documents", "database_path", "load_questions"]


# ---------- connections (created once) ----------
@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def get_client():
    # ":memory:" is only used by the tests; normally Qdrant runs in Docker
    if QDRANT_URL == ":memory:":
        return QdrantClient(location=":memory:")
    return QdrantClient(url=QDRANT_URL)


def get_vector_store():
    return QdrantVectorStore(
        client=get_client(), collection_name=COLLECTION_NAME, embedding=get_embeddings()
    )


def _only(db_id):
    """Qdrant filter on the document metadata: keep one database."""
    return models.Filter(must=[
        models.FieldCondition(key="metadata.db_id", match=models.MatchValue(value=db_id))
    ])


def _check(db_id):
    if db_id not in DATABASES:
        raise ValueError(f"Unknown database '{db_id}'. Use one of {DATABASES}.")


# ---------- public API ----------
def list_databases():
    return list(DATABASES)


def get_retriever(db_id, k=TOP_K):
    """A LangChain retriever: retriever.invoke(question) -> list of Documents."""
    _check(db_id)
    return get_vector_store().as_retriever(search_kwargs={"k": k, "filter": _only(db_id)})


def search_schema(question, db_id, k=TOP_K, rerank=False, fetch_k=FETCH_K,
                  expand_fk=False, min_links=2, max_extra=3):
    """[{table, text, source, score, vector_score}] best first. `source` is the citation.

    rerank=False: the k closest tables in Qdrant (vector similarity).
    rerank=True : take fetch_k candidates from Qdrant, reorder them with a cross-encoder,
                  keep the best k. `score` is then the reranker score; `vector_score`
                  is always the Qdrant similarity.
    expand_fk=True: after that, append the tables that link the retrieved ones (foreign keys).
                  They come last, with via="fk" and score=None. See retrieval/fk_expand.py.
    """
    _check(db_id)
    n = max(k, fetch_k) if rerank else k
    hits = get_vector_store().similarity_search_with_score(question, k=n, filter=_only(db_id))
    results = [
        {"table": doc.metadata["table"], "text": doc.page_content,
         "source": doc.metadata["source"], "score": round(score, 4),
         "vector_score": round(score, 4)}
        for doc, score in hits
    ]
    if rerank:
        from data_engineering.retrieval.rerank import rerank_hits  # loaded only when needed
        results = rerank_hits(question, results, top_n=k)
    if expand_fk:
        from data_engineering.retrieval.fk_expand import expand_with_fk  # imported here: avoids a circular import
        results = results + expand_with_fk(db_id, results, min_links, max_extra)
    return results


def get_schema_text(db_id):
    """Every table of the database, as in the documents (useful as a no-RAG baseline)."""
    _check(db_id)
    docs = [json.loads(line) for line in open(PROCESSED_DIR / "documents.jsonl", encoding="utf-8")]
    return "\n\n".join(d["text"] for d in docs if d["metadata"]["db_id"] == db_id)


def get_table_documents(db_id):
    """{table name in lower case: {table, text, source}} for one database, read from documents.jsonl."""
    _check(db_id)
    docs = [json.loads(line) for line in open(PROCESSED_DIR / "documents.jsonl", encoding="utf-8")]
    return {d["metadata"]["table"].lower(): {"table": d["metadata"]["table"], "text": d["text"],
                                             "source": d["metadata"]["source"]}
            for d in docs if d["metadata"]["db_id"] == db_id}


def load_questions(split="dev"):
    """split="dev": to build and tune the agent. split="eval": ONLY for the final benchmark."""
    if split not in ("dev", "eval"):
        raise ValueError('split must be "dev" or "eval"')
    path = QUESTIONS_DIR / f"{split}.jsonl"
    return [json.loads(line) for line in open(path, encoding="utf-8")]
