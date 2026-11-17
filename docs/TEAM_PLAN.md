# Team plan: three independent workstreams

The project is split by technical ownership, not by isolated screens. Each person owns an
end-to-end subsystem, tests it, documents it and integrates through the contracts.

## Person A — Data Engineering, RAG and retrieval evaluation
**Owns:** `data_engineering/`, `data/`, `evaluation/datasets/`, `evaluation/retrieval/`, relevant tests,
`dvc.yaml`, `params.yaml`.

| Week | Work | Deliverable |
|---|---|---|
| 1 | DVC dataset setup; schema extraction; cleaning; metadata and glossary document creation | reproducible clean data + cleaning report |
| 2 | embeddings, ChromaDB index, database routing, schema context, citations | callable retrieval module |
| 3 | retrieval benchmark and error analysis; read-only data endpoints; integration handoff | metrics + working data endpoints |
| 4 | hybrid retrieval experiment / reranker only if baseline shows a need; documentation and final report | baseline-vs-improved results + handoff |

**Acceptance:** `dvc repro` builds A's artifacts; `pytest` passes; B can use the frozen Python API;
C can browse databases/schema/quality report; retrieval metrics are reproducible.

## Person B — Agent, LangGraph, MCP and generation evaluation
**Owns:** `agent/`, `agent/api/` and chat/session routes,
`evaluation/generation/`, agent tests. B mounts A's data router rather than reimplementing it.

| Week | Work | Deliverable |
|---|---|---|
| 1 | choose LLM; SQL safety policy; read-only executor; unit tests; test A's schema-context contract | safe SQL execution foundation |
| 2 | LangGraph workflow: rewrite, retrieve, generate, validate, execute, repair, answer | working agent graph |
| 3 | MCP server exposing schema, validation, execution and chart tools; FastAPI chat + SSE | tool-calling agent integrated with C |
| 4 | generation benchmark: execution accuracy, repair, refusal, safety, follow-up handling | generation metrics + failure analysis |

**Acceptance:** LangGraph is genuinely used; tools are callable through MCP; unsafe SQL is blocked;
generation evaluation is repeatable; chat API follows `docs/CONTRACTS.md`.

## Person C — Frontend, integration and deployment
**Owns:** `frontend/`, `deploy/`, frontend tests and end-to-end tests.

| Week | Work | Deliverable |
|---|---|---|
| 1 | React + TypeScript + Vite setup; app shell; API mock from contracts | navigable application shell |
| 2 | chat interface, streaming agent timeline, SQL/result/chart/source views | functional mock-driven chat |
| 3 | database picker, schema explorer, data-quality dashboard, history/export | complete application features |
| 4 | integrate real API; Docker Compose; CI; end-to-end tests; demo and user guide | reproducible deployed application |

**Acceptance:** app works against the mock before B's API is ready; then integrates without
changing the agreed API contract; `docker compose up` launches the application.

## Shared integration rules
1. Agree on `docs/CONTRACTS.md` before parallel implementation.
2. A owns retrieval and data endpoints; B owns agent/chat endpoints; C owns the UI.
3. B must not parse BIRD description CSVs directly. B calls A's retrieval/schema API.
4. C can use mocked JSON/SSE events until B's backend is ready.
5. Changes to shared contracts require a PR and approval from affected owners.
6. Every workstream contributes tests, documentation and a short section to the final report.

## Milestones
- **M1 (end week 1):** DVC pull works for all; A's cleaned schema is available; C's mock UI runs.
- **M2 (end week 2):** A's retrieval API works; B's safe SQL executor and initial graph work.
- **M3 (end week 3):** one end-to-end question works through UI, API, agent, MCP and RAG.
- **M4 (end week 4):** retrieval + generation benchmarks, deployment, report and demo are complete.
