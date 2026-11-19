"""Add the 'linking' tables that Qdrant often misses, using the database's own foreign keys.

Problem: a question like "which driver won the most races?" needs drivers + races, but the SQL
also has to JOIN through the table `results`. That table does not look like the question,
so vector search (and the reranker) often leaves it out and the LLM cannot write the JOIN.

Idea: SQLite knows which tables are linked (FOREIGN KEY declarations). After the search, we look at
the tables we found and add the tables that link them together.

  min_links=2 (default)  add a table only if it is linked to at least 2 retrieved tables  (a "bridge")
  min_links=1            add any table directly linked to a retrieved table (more tables, more noise)
  max_extra              never add more than this many tables
"""
import sqlite3
from functools import lru_cache

from data_engineering.config import database_path
from data_engineering.data_api import get_table_documents


@lru_cache(maxsize=None)
def _load_graph(path):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        graph = {t.lower(): set() for t in tables}
        for table in tables:
            quoted = table.replace('"', '""')
            for row in conn.execute(f'PRAGMA foreign_key_list("{quoted}")'):
                other = row[2].lower()                      # row[2] = referenced table
                graph[table.lower()].add(other)
                graph.setdefault(other, set()).add(table.lower())
    finally:
        conn.close()
    return graph


def get_fk_graph(db_id):
    """{table: {linked tables}} (lower case), from the FOREIGN KEY declarations of the SQLite file."""
    return _load_graph(database_path(db_id).as_posix())


def pick_bridge_tables(graph, retrieved, min_links=2, max_extra=3):
    """Names (lower case) of the tables to add. `retrieved` is ordered best first."""
    retrieved = [t.lower() for t in retrieved]
    already = set(retrieved)
    links, best_rank = {}, {}
    for rank, table in enumerate(retrieved):
        for neighbour in graph.get(table, ()):
            if neighbour not in already:
                links[neighbour] = links.get(neighbour, 0) + 1
                best_rank.setdefault(neighbour, rank)   # linked to our best-ranked table first
    candidates = [n for n, count in links.items() if count >= min_links]
    candidates.sort(key=lambda n: (-links[n], best_rank[n], n))
    return candidates[:max_extra]


def expand_with_fk(db_id, hits, min_links=2, max_extra=3):
    """Extra tables (same format as search_schema hits, with via='fk') to add to `hits`."""
    names = pick_bridge_tables(get_fk_graph(db_id), [h["table"] for h in hits], min_links, max_extra)
    docs = get_table_documents(db_id)
    return [{**docs[n], "score": None, "vector_score": None, "via": "fk"} for n in names if n in docs]
