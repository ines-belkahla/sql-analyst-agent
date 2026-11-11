# Conversational SQL Analyst

A manager asks a business question in plain language. The system retrieves relevant database
documentation (RAG), generates and validates SQL, executes it read-only, repairs errors, and
returns a result table, chart, explanation and citations.

**Dataset:** BIRD Mini-Dev. Check and retain the dataset's licence and attribution in the final report.
**Architecture:** Person A (data/RAG) + Person B (LangGraph/MCP agent) + Person C (React application).


| Workstream | Included here | Owner |
|---|---|---|
| Data ingestion, cleaning, schema metadata, glossary documents | pipeline code and tests | A |
| Embeddings, ChromaDB index, routing, retrieval, schema context and citations | implementation and tests | A |
| Retrieval benchmark | evaluation pipeline | A |
| Read-only database/schema/quality API routes | `data_engineering/api/routes_data.py` | A |
| LangGraph, LangChain, MCP, SQL generation/execution, chat API | documented interfaces; implementation left open | B |
| React frontend, visualizations, deployment | documented interfaces; implementation left open | C |

Start with `docs/PERSON_A_GUIDE.md`, then read `docs/ARCHITECTURE.md` and
`docs/CONTRACTS.md`. `docs/TEAM_PLAN.md` defines all three workstreams.

## Repository layout

The source tree is separated by engineering responsibility. There is no generic `backend/` folder.

```text
data_engineering/             PERSON A — data and RAG implementation
  config.py                   paths, parameters and dataset discovery
  schema_store.py             cleaned schema access
  ingestion/                  source connectors and ingestion adapters
  processing/                 BIRD cleaning and document generation
  retrieval/                  embeddings, ChromaDB, routing and citations
  api/                        read-only schema and data-quality routes
agent/                        PERSON B — LangGraph, LangChain and MCP
  graph/                      LangGraph workflow [B]
  tools/                      LangChain tools and SQL safety [B]
  mcp/                        MCP server and adapters [B]
  api/                        FastAPI chat/session API [B]
frontend/                     PERSON C — React + TypeScript application
deploy/                       PERSON C — Docker Compose and deployment
data/                         datasets and generated data artifacts
  raw/                        BIRD data, tracked by DVC (not in this ZIP)
  processed/                  cleaned schema, documents and quality report
  index/                      ChromaDB index
  glossary/                    human-authored business definitions
evaluation/                   BENCHMARKING — separate from runtime code
  datasets/                   deterministic benchmark-set construction
  data/                       evaluation questions
  retrieval/                  Person A retrieval metrics
  generation/                 Person B generation metrics
  results/                    generated benchmark outputs
docs/                         architecture, contracts, plans and handoff guides
dvc.yaml                      reproducible data + retrieval pipeline
params.yaml                   pipeline and retrieval parameters
```

## 0. Prerequisites

On Windows, install:
- Python 3.11 (recommended for a predictable environment)
- Git
- Node.js LTS (Person C)
- A DagsHub account and a DagsHub repository connected to the team's GitHub repository

Use one shared GitHub repository and invite the other two teammates as collaborators.
Create the repository before pushing. Do not put dataset files, model weights, API keys or
DagsHub tokens in Git.

## Docker setup (recommended for the team)

Docker Desktop is already installed? Make sure it is running, then use the commands below
from the project root. The shared development container uses Python 3.11 and the same
`requirements.txt` for all teammates. The project folder is bind-mounted, so edits made in VS
Code on Windows appear immediately inside the container. The Hugging Face model cache is kept
in a named Docker volume. DVC configuration and credentials remain in your local project
folder; they are not baked into the image.

Build and start the development container:

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Open a shell inside it:

```powershell
docker compose exec dev bash
```

Or run commands directly without opening a shell:

```powershell
docker compose exec dev python -m pytest -q
docker compose exec dev dvc remote list
docker compose exec dev dvc pull
docker compose exec dev dvc repro
```

After editing `requirements.txt` or `Dockerfile`, rebuild the image:

```powershell
docker compose build --no-cache
docker compose up -d
```

Stop the container but keep the model cache:

```powershell
docker compose down
```

To also delete the named model-cache volume (normally unnecessary):

```powershell
docker compose down -v
```

**Important:** do not run `docker compose down -v` unless you intentionally want to delete the
local Hugging Face cache. Your source code and DVC data are bind-mounted from the project
folder and are not stored in that named volume.

For a future integrated deployment, Person B and C can add separate agent/API and frontend
services to `compose.yaml`. Do not create a separate container for every source folder;
containers should represent independently running services.

## 1. Put this project in your Git repository

Copy the ZIP contents into the team's Git repository folder. Open PowerShell in the project
root (the folder containing `README.md`).

**If the GitHub repository is brand new and has no `main` branch yet**, make the first commit
directly on `main`:

```powershell
git status
git branch -M main
git add .
git commit -m "Add Person A data and retrieval foundation"
git push -u origin main
```

**If `main` already exists**, create a feature branch and open a Pull Request:

```powershell
git checkout main
git pull origin main
git checkout -b setup/person-a
git add .
git commit -m "Add Person A data and retrieval foundation"
git push -u origin setup/person-a
```

If you have not cloned the GitHub repository yet:

```powershell
git clone https://github.com/<github-username>/<repository-name>.git
cd <repository-name>
# Copy/extract the ZIP contents into this folder, then follow the matching commands above.
```

Do not overwrite an existing `.git` folder when extracting the ZIP.

## 2. Create and activate the Python environment

Run from the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

If PowerShell blocks environment activation, run this once in the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Replacing an existing GitHub project while preserving its DVC remote

If this project is replacing an older repository, clone/use the existing repository folder and
make a backup before copying these files. Do not copy the ZIP's `.git` or `.dvc` directories
over your existing ones. Keep the existing `.git` history and `.dvc/config` /
`.dvc/config.local`. Pull any old DVC-tracked dataset you still need before replacing the old
working tree. Then copy the new project files into the repository root, preserving `.git` and
`.dvc`, review `git status`, and commit the replacement. The new `dvc.yaml` pipeline may have
different stages from the old project, so check the DVC stages and migrate/re-track the dataset
under the new `data/raw/` location as described below.

## 3. Configure DVC with DagsHub

Create a DagsHub repository connected to the team's GitHub repository. In DagsHub, open the
repository and copy its DVC remote URL. It normally looks like:

`https://dagshub.com/<dagshub-username>/<repository-name>.dvc`

Add the remote (replace placeholders with the real values):

```powershell
dvc init
dvc remote add -d origin https://dagshub.com/<dagshub-username>/<repository-name>.dvc
git add .dvc/config
git commit -m "Configure DVC remote"
git push
```

Configure your own credentials locally. Get a DagsHub access token from your DagsHub account
settings; do not paste it into a tracked file.

```powershell
dvc remote modify origin --local auth basic
dvc remote modify origin --local user <dagshub-username>
dvc remote modify origin --local password <dagshub-access-token>
```

The `--local` settings are stored in `.dvc/config.local` and must never be committed.
Each teammate configures their own credentials on their own machine.

If `dvc init` reports that DVC is already initialized, do not initialize it again. Check
`.dvc/config` and continue with the remote setup.

## 4. Download and track BIRD Mini-Dev

Download the **BIRD Mini-Dev Complete Package** from the official BIRD dataset page:
https://bird-bench.github.io/

Extract its contents under `data/raw/`. The directory can contain a wrapper folder, but the
pipeline must be able to find both:
- `dev_databases/` with each `<database>/<database>.sqlite` file and optional
  `database_description/*.csv` files
- `mini_dev_sqlite.json`

Check that the project can discover the files:

```powershell
python -c "from data_engineering import config; print(config.dev_databases_dir()); print(config.questions_file()); print(config.list_db_ids())"
```

Track the raw data with DVC:

```powershell
dvc add data/raw
git add data/raw.dvc data/.gitignore
git commit -m "Track BIRD Mini-Dev with DVC"
git push
dvc push
```

The raw dataset is deliberately **not included in this ZIP**. This avoids shipping a large
dataset copy and keeps Git lightweight. DVC stores the dataset artifacts.

## 5. Run Person A's pipeline

First run the unit tests. The tests use a small synthetic BIRD-like fixture and a fake embedder,
so they do not need the full dataset or a model download:

```powershell
python -m pytest -q
```

Then run the complete DVC pipeline:

```powershell
dvc repro
```

Stages:
1. `build_eval_set`: select a deterministic, stratified evaluation sample.
2. `clean`: create `schema.json`, `documents.jsonl` and `cleaning_report.json`.
3. `index`: embed documents and build the persistent ChromaDB index.
4. `eval_retrieval`: compute retrieval metrics and detailed results.

The first index build downloads the configured embedding model (`BAAI/bge-small-en-v1.5`).
Allow time and disk space for this download.

Useful commands:

```powershell
dvc repro clean
dvc repro index
dvc repro eval_retrieval
dvc status
dvc metrics show
```

Inspect:
- `data/processed/schema.json`
- `data/processed/documents.jsonl`
- `data/processed/cleaning_report.json`
- `evaluation/results/retrieval_metrics.json`
- `evaluation/results/retrieval_details.csv`

After successful reproduction, publish the DVC artifacts and commit the reproducibility files:

```powershell
dvc push
git add dvc.lock evaluation/data/eval_set.jsonl evaluation/results/retrieval_metrics.json
git commit -m "Add reproducible cleaned data and retrieval benchmark"
git push
```

Note: `data/processed` and `data/index` are declared as pipeline outputs in `dvc.yaml`.
DVC records their versions in `dvc.lock` and uploads their cache with `dvc push`; they do not
need separate `dvc add` commands or standalone `.dvc` pointer files.

## 6. Verify Person A's retrieval API

```powershell
python -c "from data_engineering.retrieval.context import build_schema_context; c=build_schema_context('Which drivers scored the most points?'); print(c.db_id); print(c.tables); print(c.citations[:3])"
```

The main interface for Person B is:

```python
from data_engineering.retrieval.context import build_schema_context

context = build_schema_context(
    question="Which drivers scored the most points?",
    db_id=None,  # None means automatic database routing
)
print(context.db_id)
print(context.text)
print(context.citations)
```

Person A's data router can be mounted by Person B:

```python
from data_engineering.api.routes_data import router as data_router
app.include_router(data_router, prefix="/api")
```

It provides:
- `GET /api/databases`
- `GET /api/databases/{db_id}/schema`
- `GET /api/quality-report`

Person B owns `/api/health`, `/api/chat`, sessions, streaming and the agent.

## 7. Git and DVC workflow for all three people

Each person should work on a feature branch and avoid editing another person's folders without
coordination.

```powershell
git checkout main
git pull
dvc pull
git checkout -b <person>/<feature>
# Make changes in your owned folders
python -m pytest -q
git status
git add <changed-files>
git commit -m "Describe the change"
git push -u origin <person>/<feature>
```

Open a PR into `main`. For changes to DVC-tracked artifacts:

```powershell
dvc repro
dvc push
git add dvc.lock <relevant-metrics-or-eval-files>
git commit -m "Update data pipeline artifacts"
git push
```

For teammates B and C, the first-time setup after cloning is:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
# Configure your own DagsHub credentials as in section 3
dvc pull
python -m pytest -q
```

Person C also installs the frontend dependencies from `frontend/` once that workstream creates
its `package.json`:

```powershell
cd frontend
npm install
npm run dev
```

## 8. Troubleshooting

| Problem | What to check |
|---|---|
| `dev_databases/ not found` | Dataset extraction path and `dvc pull`; run the discovery command in section 4 |
| `mini_dev_sqlite.json not found` | Dataset package/version and extracted directory |
| `schema.json missing` | Run `dvc pull` or `dvc repro clean` |
| DVC 401/403 | DagsHub token, username, repository permissions and local remote credentials |
| `No module named data_engineering or evaluation` | Activate `.venv`, run `pip install -e .` from project root |
| Embedding download fails | Network/cache issue; retry after checking model access and disk space |
| Teammate cannot see data | Ensure `dvc push` completed and teammate ran `dvc pull` |
| Git rejects a large file | Remove raw data from Git tracking; use `dvc add data/raw` and commit the `.dvc` pointer |

## 9. Final project evidence

The final report/demo should include:
- data provenance, cleaning decisions, metadata model and glossary;
- sample retrieved documents with source citations;
- retrieval benchmark baseline and improved system (if hybrid retrieval is implemented);
- LangGraph workflow and actual MCP tool calls;
- SQL safety tests and read-only execution;
- generation benchmark and error analysis;
- end-to-end web application and deployment instructions;
- limitations, reproducibility instructions and dataset attribution.
