"""Read access to the CLEANED schema (data/processed/schema.json). Owner: Person A.
Used by: retrieval (A), agent prompts / validator allow-lists (B), schema explorer endpoint (B -> C)."""
import json
from functools import lru_cache
from . import config


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict:
    return json.loads(open(path, encoding="utf-8").read())


def load_schemas() -> dict:
    p = config.processed_dir() / "schema.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing. Run `dvc pull` or `dvc repro clean`.")
    return _load(str(p), p.stat().st_mtime)


def get_schema(db_id: str) -> dict:
    return load_schemas()[db_id]


def list_databases() -> list[dict]:
    """[{db_id, n_tables, n_columns}] for the database picker in the UI."""
    return [{"db_id": d, "n_tables": len(s["tables"]),
             "n_columns": sum(len(t["columns"]) for t in s["tables"])}
            for d, s in sorted(load_schemas().items())]
