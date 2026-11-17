# Person A: implementation guide (the work included in this ZIP)

## Ownership
Person A owns the complete data and retrieval layer:
- `data_engineering/config.py` and `data_engineering/schema_store.py`
- `data_engineering/processing/` (cleaning and document preparation)
- `data_engineering/retrieval/` (embeddings, indexing, routing, retrieval and citations)
- `data_engineering/api/` (read-only schema and data-quality routes)
- `data/`, `evaluation/datasets/`, `evaluation/retrieval/` and `tests/data_engineering/`
- `dvc.yaml` and `params.yaml` (coordinate shared changes with B)

Person B owns the separate top-level `agent/` package and `evaluation/generation/`. Person C owns `frontend/` and `deploy/`. Person A does not implement LangGraph, MCP, SQL generation/execution, chat/session endpoints, frontend screens or deployment.

## Work packages and acceptance criteria

### A1. Dataset and reproducibility
- Obtain BIRD Mini-Dev and preserve its licence/attribution.
- Track `data/raw/` with DVC, not Git.
- Ensure a teammate can clone the Git repository, configure their own DagsHub credentials,
  run `dvc pull`, and reproduce the pipeline.
- Keep credentials in `.dvc/config.local` or environment variables, never commit tokens.

**Done when:** raw data is available via DVC and the pipeline runs from a clean clone.

### A2. Cleaning and document management
- Inspect `cleaning_report.json` and resolve unexpected missing/mismatched metadata.
- Validate table/column descriptions, primary and foreign keys, sample values and glossary entries.
- Keep stable document IDs, source metadata and content hashes.
- Ensure every retrieved document has a source that can be cited in the UI.
- Document the input/output schema and data provenance.

**Done when:** `schema.json`, `documents.jsonl` and `cleaning_report.json` are reproducible,
deterministic and covered by tests.

### A3. Retrieval
- Build and persist the ChromaDB index.
- Implement database routing and top-k schema retrieval.
- Build compact schema context, foreign-key expansion and citations.
- Measure baseline dense retrieval before attempting improvements.
- If time permits, add BM25 + dense hybrid retrieval and compare it to the baseline.

**Done when:** B can call `build_schema_context(question, db_id=None)` without depending on
raw CSVs or knowing how the index is built.

### A4. Retrieval benchmark
- Keep a deterministic, stratified evaluation set.
- Report Recall@3, Recall@5, Recall@10, MRR, database-routing accuracy and context recall.
- Break results down by question difficulty and known-database vs auto-routed mode.
- Keep a held-out subset for tuning discipline; do not tune against all evaluation questions.
- Record baseline and improved results in `evaluation/results/` and explain failure cases.

**Done when:** a reproducible command generates machine-readable metrics and a short analysis.

### A5. Data endpoints and handoff
- Implement and test `/api/databases`, `/api/databases/{db_id}/schema` and `/api/quality-report`.
- Coordinate with B before changing shared response contracts.
- Give C stable sample JSON responses and endpoint documentation.

**Done when:** B can mount `data_engineering.api.routes_data.router` and C can consume the documented endpoints.

## Suggested schedule (4 weeks)
| Week | Deliverable |
|---|---|
| 1 | Dataset tracked in DVC, cleaning pipeline validated, data dictionary and cleaning report |
| 2 | Vector index, database routing, schema context and citations |
| 3 | Retrieval benchmark, error analysis, data endpoints, integration with B and C |
| 4 | Hybrid retrieval experiment if justified, final metrics, documentation and handoff |

## Commands
See the root `README.md` for the exact Windows PowerShell setup, DVC remote configuration,
pipeline execution, testing, Git branching and push workflow.
