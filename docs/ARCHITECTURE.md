# Architecture and tools

```
 Browser (React app)  <-- REST + SSE -->  FastAPI  -->  LangGraph agent  --> LLM
        C                                   B               B
                                              |  tools (also exposed through an MCP server)
                         explain_schema  validate_sql  run_sql  make_chart
                               |               |           |
                  A: build_schema_context   B: sqlglot   B: SQLite read-only
                               |
        A: Chroma index <- documents.jsonl <- CLEANING <- BIRD databases + CSV descriptions + glossary  (DVC / DagsHub)
```
Per question: rewrite follow-up (memory) -> schema retrieval (A) -> SQL generation -> safety validation -> read-only execution
-> repair loop (up to 3) -> table + chart + explanation + sources, streamed step by step to the UI.

## Tools
| Area | Tool | Used by |
|---|---|---|
| Language | Python 3.11+ | A, B |
| Data versioning | DVC + DagsHub (remote storage, pipeline, metrics) | all |
| Cleaning | csv, sqlite3, pandas | A |
| Vector store / embeddings | ChromaDB, sentence-transformers (BAAI/bge-small-en-v1.5) | A |
| SQL parsing and safety | sqlglot, SQLite `mode=ro` | B |
| Agent framework | LangGraph + LangChain chat models (any LLM provider) | B |
| Tool protocol | MCP (`mcp<2`, FastMCP) | B |
| API | FastAPI, uvicorn, Server-Sent Events | B |
| Frontend | React + TypeScript + Vite, Tailwind, a chart library (Recharts), TanStack Query | C |
| Delivery | Docker Compose, GitHub Actions, pytest, Playwright (suggested) | C |
| Observability (optional) | Langfuse or LangSmith traces | B |

## How the three lanes stay in sync
1. **Contracts first** (`docs/CONTRACTS.md`): A to B is a Python API, B to C is a REST/SSE API. Nobody waits: C builds on a mock, B builds on A's real data from day 2.
2. **One owner per folder** (`.github/CODEOWNERS`); shared files (`dvc.yaml`, `requirements.txt`) are edited in small PRs.
3. **Data flows through DVC**: A publishes `data/processed` and `data/index`; B and C only `dvc pull`.
4. **Integration milestones** (TEAM_PLAN): M1 data and retrieval, M2 streaming chat stub, M3 end-to-end, M4 evaluation and freeze.
5. **Breaking a contract** needs a PR that edits `CONTRACTS.md` and is approved by both sides.
