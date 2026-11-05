import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Folders
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BIRD_DIR = DATA_DIR / "bird"            # cleaned dataset (made by download_data.py)
DATABASES_DIR = BIRD_DIR / "databases"  # one SQLite file per database
VECTOR_STORE_DIR = DATA_DIR / "vectorstore"  # FAISS index (made by ingest.py)
RESULTS_DIR = ROOT / "results"          # evaluation results (made by evaluate.py)

# Files
QUESTIONS_FILE = BIRD_DIR / "questions.json"
DESCRIPTIONS_FILE = BIRD_DIR / "descriptions.csv"

# Models
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

# Retrieval and safety
TOP_K = 5             # number of tables returned by the retriever
ROW_LIMIT = 200       # max rows returned by a query
TIMEOUT_SECONDS = 10  # max execution time of a query


def database_path(db_id: str) -> Path:
    return DATABASES_DIR / db_id / f"{db_id}.sqlite"


def list_databases() -> list[str]:
    return sorted(p.name for p in DATABASES_DIR.iterdir() if p.is_dir())
