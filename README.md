# Conversational SQL Analyst

A manager asks a business question in plain language. The system finds the relevant tables
(RAG), writes SQL, runs it read-only, and answers with a table, a chart, an explanation and its
sources.

**Team:** Ines Belkahla (A: data and retrieval), Ouissem Oueslati, Sarra Bettaieb
(B: agent, C: interface).
**Data:** 3 databases of [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) (CC BY-SA 4.0):
`financial`, `formula_1`, `student_club`.

## How the data part works

```
BIRD download ─► select_subset ─► data/raw (3 databases + their questions)        [DVC]
                                    │
                                    ├─► clean ─► data/processed/documents.jsonl    [DVC]
                                    │            one document per table, from BIRD's
                                    │            descriptions, Czech values translated
                                    │
                                    └─► build_eval_set ─► data/questions/dev|eval  [Git]

documents.jsonl ─► index ─► Qdrant (Docker) ─► data_api.py ─► Person B's agent
                                                    └─► eval_retrieval: Recall@k, Precision@k, MRR
```

| Requirement | Where |
| --- | --- |
| RAG | `processing/clean.py` builds the documents, `retrieval/index.py` embeds them in Qdrant, `data_api.py` retrieves them |
| Metadata | every document has `db_id`, `table`, `source` and a content `hash` (used to skip unchanged documents) |
| Citation | every search result carries its `source` file |
| Documentation | this README, `DATA_API.md`, and `data/processed/cleaning_report.json` |
| Framework | LangChain (`langchain-qdrant`, `langchain-huggingface`) |
| Retrieval benchmark | `evaluation/retrieval/eval_retrieval.py` |

```
data_engineering/
  config.py               settings: the 3 databases, paths, Qdrant, model
  select_subset.py        step 0: keep our 3 databases from the BIRD download
  processing/clean.py     step 1: clean descriptions, one document per table
  retrieval/index.py      step 2: store the documents in Qdrant
  data_api.py             what Person B imports (see DATA_API.md)
evaluation/
  datasets/build_eval_set.py   step 3: dev / eval question split
  retrieval/eval_retrieval.py  step 4: retrieval benchmark
tests/                    the pipeline on a tiny fake dataset (no Docker, no download)
docker-compose.yml        Qdrant, as in the course
dvc.yaml                  the pipeline
```

## Setup (everyone, once) — Git Bash, Python 3.11

```bash
git clone https://github.com/ines-belkahla/sql-analyst-agent.git
cd sql-analyst-agent
py -3.11 -m venv vtest
source vtest/Scripts/activate          # in every new terminal
pip install -r requirements.txt
python -m pytest -q                    # 5 passed
```

Connect to DagsHub with **your own** username and token (DagsHub > avatar > Your Settings > Tokens):

```bash
dvc remote modify origin --local auth basic
dvc remote modify origin --local user <your-dagshub-username>
dvc remote modify origin --local password <your-dagshub-token>
```

## Get the data (everyone)

```bash
dvc pull                                       # data/raw, data/processed
docker compose up -d                           # Qdrant (Docker Desktop must be running)
python -m data_engineering.retrieval.index     # documents -> Qdrant, a few seconds
```

Qdrant's dashboard: http://localhost:6333/dashboard

## Person A: changing the data

After editing the cleaning code or the list of databases:

```bash
dvc repro clean build_eval_set
python -m data_engineering.retrieval.index
dvc repro eval_retrieval
dvc metrics show
dvc push
git add .
git commit -m "Describe the change"
git push
```

Teammates then run `git pull`, `dvc pull` and the index command.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ModuleNotFoundError` | `source vtest/Scripts/activate`, then `pip install -r requirements.txt` |
| Connection refused on port 6333 | start Docker Desktop, then `docker compose up -d` |
| Search returns nothing | `python -m data_engineering.retrieval.index` |
| `dvc pull` gives 401 or 403 | redo the three `dvc remote modify ... --local` lines |
| `data/raw` missing | `dvc pull` |
