# Contracts between the lanes
Changing anything here needs a PR approved by both sides.

## 1. Person A -> Person B (Python)
```python
from data_engineering.retrieval.context import build_schema_context, SchemaContext, Citation
from data_engineering.retrieval.search  import search, route_db, rank_tables, Hit
from data_engineering            import config, schema_store
```
| Call | Returns |
|---|---|
| `build_schema_context(question, db_id=None, k=None)` | `SchemaContext(db_id, text, tables, definitions, citations)`. `text` is prompt-ready (tables, columns, types, descriptions, examples, foreign keys, glossary definitions). `db_id=None` means the retriever picks the database. `.to_dict()` is JSON-ready. **B wraps this as the MCP tool `explain_schema`.** |
| `search(question, db_id=None, k=None)` | `list[Hit(id, text, score, db_id, table, column, level, source)]` |
| `route_db(question)` | the best `db_id` |
| `config.sqlite_path(db_id)`, `config.list_db_ids()` | path of the `.sqlite` file (B opens it with `mode=ro`), the 11 database ids |
| `schema_store.get_schema(db_id)`, `schema_store.list_databases()` | cleaned schema dict, `[{db_id, n_tables, n_columns}]` |

Rules: A never executes user SQL; B never reads `data/raw` CSVs directly. Call a first `build_schema_context("warm up")` at server start (the embedding model loads once).
`Citation.source` is what the UI shows as the source (`database_description/drivers.csv`, `glossary/formula_1.md`, `sqlite schema`).

### Data files (DVC outputs, read-only for B and C)
* `data/processed/schema.json`: `{db_id: {db_id, tables: [{name, n_rows, source, primary_key[], foreign_keys[{from,to_table,to_column}], columns[{name,type,is_pk,human_name,description,description_source('csv'|'auto'),value_description,data_format,samples[]}]}]}}`
* `data/processed/cleaning_report.json`: `{summary: {...counts...}, details: {...lists...}}`
* `evaluation/data/eval_set.jsonl`: one JSON per line `{id, db_id, question, evidence, gold_sql, difficulty, gold_tables[]}`

## 2. Person B -> Person C (REST, JSON, base path `/api`)
| Method and path | Owner | Purpose |
|---|---|---|
| `GET /health` | B | `{"status":"ok"}` |
| `GET /databases` | A (router `routes_data.py`) | `[{db_id, n_tables, n_columns}]` |
| `GET /databases/{db_id}/schema` | A | one entry of `schema.json` (schema explorer) |
| `GET /quality-report` | A | `cleaning_report.json` (data quality page) |
| `POST /chat` | B | body below; response is an SSE stream (section 3) or, with `?stream=false`, one JSON |
| `GET /sessions/{session_id}` / `DELETE` | B | conversation history / reset |

`POST /chat` body: `{"session_id": "abc", "message": "and for 2012?", "db_id": null, "use_memory": true, "evidence": ""}`
(`db_id: null` = auto-detect). `?stream=false` response:
```json
{"standalone_question": "Which 5 drivers scored the most points in 2012?", "db_id": "formula_1",
 "sql": "SELECT ...", "attempts": 1, "refused": false,
 "result": {"columns": ["driver", "points"], "rows": [["Vettel", 281]], "row_count": 1, "truncated": false},
 "chart": {"type": "bar", "x": "driver", "labels": ["Vettel"], "series": {"points": [281]}},
 "answer": "Vettel scored the most points in 2012 ...",
 "sources": {"tables": ["drivers", "results"], "definitions": [],
             "citations": [{"id": "formula_1.results.points", "source": "database_description/results.csv", "score": 0.81}]}}
```
Person C builds against a mock (for example MSW or a small JSON server) returning exactly this shape until B is ready.

## 3. Streaming events of `POST /chat` (`text/event-stream`, one `event:` + `data:` JSON each)
`status {step}` (rewrite, retrieve, generate, validate, execute, repair, present) · `standalone_question {text}` ·
`sources {db_id, tables, citations[], definitions[]}` · `sql {attempt, sql}` · `attempt_failed {attempt, error}` ·
`result {columns, rows, row_count, truncated}` · `chart {type, x, labels, series}` · `answer {text, refused}` ·
`done {attempts, latency_ms}` · `error {message}`.
Order is not guaranteed except that `done` or `error` is last. `chart.type` is `bar`, `line` or `none`.
