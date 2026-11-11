"""Shared configuration. Owner: Person A. Frozen API: B and C import from here, never edit.
All paths are functions so tests can redirect them with environment variables."""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]

_DEFAULTS = {
    "clean": {"sample_values": 5, "sample_value_max_chars": 40, "value_description_max_chars": 600},
    "embedding": {"model": "BAAI/bge-small-en-v1.5",
                  "query_prefix": "Represent this sentence for searching relevant passages: "},
    "retrieval": {"k": 20, "max_tables": 6, "fk_expand": 2, "max_cols_per_table": 25},
    "eval": {"seed": 42, "n_questions": 60},
}


def _path(env: str, default: Path) -> Path:
    p = Path(os.getenv(env, default))
    return p if p.is_absolute() else ROOT / p


def raw_dir() -> Path:
    return _path("BIRD_DIR", ROOT / "data" / "raw")


def processed_dir() -> Path:
    return _path("PROCESSED_DIR", ROOT / "data" / "processed")


def index_dir() -> Path:
    return _path("INDEX_DIR", ROOT / "data" / "index")


def glossary_dir() -> Path:
    return _path("GLOSSARY_DIR", ROOT / "data" / "glossary")


@lru_cache(maxsize=1)
def params() -> dict:
    out = {k: dict(v) for k, v in _DEFAULTS.items()}
    f = ROOT / "params.yaml"
    if f.exists():
        for section, values in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).items():
            out.setdefault(section, {}).update(values or {})
    return out


def dev_databases_dir() -> Path:
    for p in raw_dir().rglob("dev_databases"):
        if p.is_dir():
            return p
    raise FileNotFoundError(f"dev_databases/ not found under {raw_dir()}. Run `dvc pull` (README step 3).")


def questions_file() -> Path:
    for p in raw_dir().rglob("mini_dev_sqlite.json"):
        return p
    raise FileNotFoundError(f"mini_dev_sqlite.json not found under {raw_dir()}.")


def list_db_ids() -> list[str]:
    return sorted(d.name for d in dev_databases_dir().iterdir() if (d / f"{d.name}.sqlite").exists())


def sqlite_path(db_id: str) -> Path:
    """Path of a BIRD SQLite file. Person B opens it read-only (mode=ro)."""
    p = dev_databases_dir() / db_id / f"{db_id}.sqlite"
    if not p.exists():
        raise FileNotFoundError(p)
    return p
