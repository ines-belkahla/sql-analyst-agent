# Scope and feature priorities

## Is the project large enough?
Yes. The core system combines a documented data/RAG pipeline, retrieval and generation
benchmarks, a LangGraph agent with MCP tools and SQL safety, and a full web application.
The three people own distinct, testable subsystems.

## Mandatory course requirements
| Requirement | Implementation | Owner | Evidence in final demo/report |
|---|---|---|---|
| Document management: RAG, metadata, citations, documentation | cleaned schema documents, glossary, metadata, provenance, ChromaDB and source citations | A | inspect indexed docs and sources panel |
| Tool calling / MCP | MCP server with schema, SQL validation, read-only execution and chart tools | B | invoke tools through MCP client |
| LangChain / LangGraph | LangGraph stateful agent, LangChain model/tool integration | B | graph diagram and live agent steps |
| Retrieval + generation benchmarking | Recall@k/MRR/routing/context recall + execution accuracy/safety/repair/refusal | A + B | metrics files and error analysis |
| Web or mobile interface | React + TypeScript web application | C | live end-to-end application |

## Feature priorities
| Feature | Owner | Priority | Notes |
|---|---|---|---|
| Document metadata, provenance and citations | A + C | Must | citation IDs and source names must reach UI |
| Database auto-detection | A | Must | benchmark routing accuracy |
| Retrieval benchmark | A | Must | report baseline and difficulty breakdown |
| LangGraph workflow and MCP tools | B | Must | demonstrate actual tool invocation |
| SQL validation and read-only execution | B | Must | safety tests, not prompt-only protection |
| Generation benchmark | B | Must | execution accuracy, repair, refusals, safety |
| Live agent steps and attempts | B + C | Should | makes orchestration observable |
| Schema explorer | A + C | Should | consumes cleaned schema endpoint |
| Data-quality dashboard | A + C | Should | consumes cleaning report endpoint |
| Hybrid retrieval (BM25 + dense) | A | Should | compare against dense baseline |
| Edit-and-rerun SQL | B + C | Should | human approval before execution |
| Export CSV and saved question history | C | Should | user-facing utility |
| Glossary editing and re-indexing | A + C | Could | only after core retrieval is stable |
| Reranker | A | Could | only if measured retrieval errors justify it |
| Fine-tuned embedding model | A | Could | optional; compare before/after Recall@k |
| LLM-as-judge | B | Could | secondary metric, not a replacement for execution accuracy |
| Langfuse / LangSmith tracing | B | Could | useful for debugging and report figures |
| Login and per-user history | B + C | Could | avoid unless core features are finished |

## Scope guardrails
- Finish all mandatory features before optional experiments.
- Do not fine-tune a model just to add a training component; first establish a baseline and a
  measurable problem.
- Do not let A own agent logic or B own raw-data cleaning.
- Do not let C build only a static chat mock: the final app must consume real APIs.
- Report limitations honestly, including benchmark size and cases where schema retrieval fails.
