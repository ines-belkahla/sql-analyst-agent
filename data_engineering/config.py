"""Shared settings for the data part (Person A). Everyone imports from here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

# The 3 BIRD databases we use (out of 11)
DATABASES = ["financial", "formula_1", "student_club"]

# Folders
DOWNLOAD_DIR = ROOT / "data" / "download"    # full BIRD package (1.5 GB, never shared)
RAW_DIR = ROOT / "data" / "raw"              # our 3 databases + their questions (shared with DVC)
PROCESSED_DIR = ROOT / "data" / "processed"  # cleaned schema + documents (shared with DVC)
QUESTIONS_DIR = ROOT / "data" / "questions"  # dev / eval question files (in Git)
RESULTS_DIR = ROOT / "evaluation" / "results"

# Vector store: Qdrant running in Docker (docker compose up -d), as in the course
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "bird_schema"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Retrieval and evaluation
TOP_K = 3              # tables returned per question
FETCH_K = 10           # candidates taken from Qdrant before reranking
RERANK_MODEL = "BAAI/bge-reranker-base"   # lighter alternative: "cross-encoder/ms-marco-MiniLM-L-6-v2"
EVAL_PER_DATABASE = 10  # frozen evaluation questions per database (the rest is dev)
SEED = 42


def database_path(db_id: str) -> Path:
    """Path of one SQLite file. Open it read-only: sqlite3.connect(f"file:{path}?mode=ro", uri=True)."""
    return RAW_DIR / db_id / f"{db_id}.sqlite"
