"""STEP 2c - SCHEMA CONTEXT for the SQL generator. Owner: Person A.
Person B wraps `build_schema_context` as the MCP tool `explain_schema` and calls it inside the agent graph.
"""
from dataclasses import dataclass, field, asdict
from data_engineering import config, schema_store
from .search import search, rank_tables, route_db


@dataclass
class Citation:
    id: str
    source: str
    score: float


@dataclass
class SchemaContext:
    db_id: str
    text: str                                   # prompt-ready schema description
    tables: list[str]
    definitions: list[str] = field(default_factory=list)   # glossary paragraphs used
    citations: list[Citation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _select_tables(hits, schema, p) -> list[str]:
    ranked = [t for t in rank_tables(hits) if t in {x["name"] for x in schema["tables"]}][: p["max_tables"]]
    by_name = {t["name"]: t for t in schema["tables"]}
    extra = []
    for t in list(ranked):                      # add tables linked by foreign keys (join paths)
        for fk in by_name[t]["foreign_keys"]:
            if fk["to_table"] in by_name and fk["to_table"] not in ranked + extra:
                extra.append(fk["to_table"])
        for o in schema["tables"]:
            if o["name"] not in ranked + extra and any(f["to_table"] == t for f in o["foreign_keys"]):
                extra.append(o["name"])
    return ranked + extra[: p["fk_expand"]]


def _render_table(t: dict, wanted_cols: set, max_cols: int) -> str:
    fk_cols = {f["from"] for f in t["foreign_keys"]}
    cols = t["columns"]
    if len(cols) > max_cols:
        cols = [c for c in cols if c["name"] in wanted_cols or c["is_pk"] or c["name"] in fk_cols]
    lines = [f"TABLE {t['name']}  ({t['n_rows']} rows)"]
    for c in cols:
        ex = f"  e.g. {', '.join(c['samples'][:3])}" if c["samples"] else ""
        vd = f" [{c['value_description'][:160]}]" if c["value_description"] else ""
        lines.append(f"  - {c['name']} {c['type']}{' PK' if c['is_pk'] else ''}: {c['description']}{vd}{ex}")
    for f in t["foreign_keys"]:
        lines.append(f"  FK {f['from']} -> {f['to_table']}.{f['to_column']}")
    return "\n".join(lines)


def build_schema_context(question: str, db_id: str | None = None, k: int | None = None) -> SchemaContext:
    """db_id=None -> the retriever picks the database (routing)."""
    p = config.params()["retrieval"]
    db_id = db_id or route_db(question, k)
    hits = search(question, db_id, k)
    schema = schema_store.get_schema(db_id)
    tables = _select_tables(hits, schema, p)
    wanted = {h.column for h in hits if h.column}
    by_name = {t["name"]: t for t in schema["tables"]}
    defs = [h.text for h in hits if h.level == "glossary"]
    parts = [_render_table(by_name[t], wanted, p["max_cols_per_table"]) for t in tables]
    if defs:
        parts.append("DEFINITIONS\n" + "\n".join(f"  - {d}" for d in defs))
    cites = [Citation(h.id, h.source, h.score) for h in hits if h.table in tables or h.level == "glossary"]
    return SchemaContext(db_id=db_id, text="\n\n".join(parts), tables=tables, definitions=defs, citations=cites)
