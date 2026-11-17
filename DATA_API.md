# Data API: how Person B uses the data

Everything comes from one module: `data_engineering/data_api.py`.
You never read the raw files yourself.

## Before you start (once per session)

```bash
source vtest/Scripts/activate                  # your virtual environment
docker compose up -d                           # starts Qdrant
dvc pull                                       # gets the cleaned data
python -m data_engineering.retrieval.index     # loads the documents into Qdrant (seconds)
```

## What you get

| Function | Returns |
| --- | --- |
| `list_databases()` | `["financial", "formula_1", "student_club"]` |
| `get_retriever(db_id, k=3)` | a LangChain retriever over that database's table documents |
| `search_schema(question, db_id, k=3)` | `[{"table", "text", "source", "score"}]`, best first |
| `get_schema_text(db_id)` | every table of the database as text (no RAG) |
| `database_path(db_id)` | path of the SQLite file |
| `load_questions("dev")` | questions + reference SQL to build and test the agent |
| `load_questions("eval")` | 30 frozen questions, **only** for the final generation benchmark |

## Examples

**Find the tables for a question (RAG) and keep the citations**

```python
from data_engineering.data_api import search_schema

hits = search_schema("How many accounts get a monthly statement?", "financial")
schema_for_prompt = "\n\n".join(h["text"] for h in hits)
sources = [h["source"] for h in hits]      # show these as citations in the answer
```

**Use it inside LangChain / LangGraph**

```python
from data_engineering.data_api import get_retriever

retriever = get_retriever("formula_1", k=3)
docs = retriever.invoke("Which drivers scored the most points in 2013?")
# each doc.metadata has: db_id, table, source
```

**As an MCP tool** (in your MCP server)

```python
@mcp.tool()
def explain_schema(db_id: str, question: str) -> list[dict]:
    """Tables of `db_id` relevant to `question`, with their source file."""
    return search_schema(question, db_id)
```

**Run SQL read-only** (your safety layer stays yours)

```python
import sqlite3
from data_engineering.data_api import database_path

conn = sqlite3.connect(f"file:{database_path('financial').as_posix()}?mode=ro", uri=True)
rows = conn.execute("SELECT COUNT(*) FROM account WHERE frequency = 'POPLATEK MESICNE'").fetchall()
```

**Test the agent on real questions**

```python
from data_engineering.data_api import load_questions

for q in load_questions("dev"):
    print(q["db_id"], q["question"], q["evidence"], q["SQL"], q["gold_tables"])
```

## Things to know

- **Czech values in `financial`.** The database stores values in Czech, and the reference SQL uses
  them as stored (`'POPLATEK MESICNE'`). The documents give the English meaning
  (`'POPLATEK MESICNE' = monthly statement`), so your SQL must keep the Czech value.
- **`evidence`** is a hint BIRD gives with each question. Report the generation benchmark with and
  without it; it is not in the documents.
- **Never tune on `load_questions("eval")`.** Those questions measure the final system.
- If `search_schema` fails with a connection error, Qdrant is not running: `docker compose up -d`.
  If it returns nothing, run `python -m data_engineering.retrieval.index`.
