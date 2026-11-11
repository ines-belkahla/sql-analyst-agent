"""STEP 2b - SEARCH. Owner: Person A. Public API used by Person B (do not break signatures)."""
from collections import defaultdict
from dataclasses import dataclass, asdict
from data_engineering import config
from . import embeddings
from .index import get_collection


@dataclass
class Hit:
    id: str
    text: str
    score: float          # cosine similarity, higher is better
    db_id: str
    table: str            # '' for glossary documents
    column: str           # '' for table/glossary documents
    level: str            # 'table' | 'column' | 'glossary'
    source: str           # citation: csv file, 'sqlite schema' or glossary file

    def to_dict(self) -> dict:
        return asdict(self)


def search(question: str, db_id: str | None = None, k: int | None = None) -> list[Hit]:
    """Top-k documents for a question, optionally restricted to one database."""
    k = k or config.params()["retrieval"]["k"]
    col = get_collection()
    kwargs = {"where": {"db_id": db_id}} if db_id else {}
    res = col.query(query_embeddings=[embeddings.embed_query(question)], n_results=k, **kwargs)
    return [Hit(id=i, text=t, score=round(1 - d, 4), db_id=m["db_id"], table=m["table"], column=m["column"],
                level=m["level"], source=m["source"])
            for i, t, d, m in zip(res["ids"][0], res["documents"][0], res["distances"][0], res["metadatas"][0])]


def rank_tables(hits: list[Hit]) -> list[str]:
    """Distinct tables in order of best hit (table, column documents; glossary ignored)."""
    seen = []
    for h in hits:
        if h.table and h.table not in seen:
            seen.append(h.table)
    return seen


def route_db(question: str, k: int | None = None) -> str:
    """Pick the database for a question: score-weighted vote of the top-k hits over ALL databases."""
    votes = defaultdict(float)
    for h in search(question, None, k):
        votes[h.db_id] += h.score
    return max(votes, key=votes.get)
