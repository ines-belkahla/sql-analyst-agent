# SQL Analyst Agent

Ask a question about a database in plain English. The agent finds the relevant tables (RAG),
writes SQL, checks that it is safe, runs it read-only, fixes its own errors, and answers with
a table, a chart, the SQL and its sources. It remembers the conversation, so follow-up
questions like "and for 2012?" work.

Team: Ouissem Oueslati, Sarra Bettaieb, Ines Belkahla.
Data: [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev), 500 questions over 11 SQLite databases.

## What covers each required feature

| Required feature | Where |
| --- | --- |
| Document management: RAG, metadata, citation | `src/ingest.py` builds one document per table with metadata (`db_id`, `table`, `source`); `src/retriever.py` searches it, filtered by database; answers cite the `source` files |
| Tool calling / MCP | `mcp_server.py` exposes `explain_schema` and `run_sql`; the agent calls them |
| Framework (LangChain / LangGraph) | `src/agent.py`: LangChain `create_agent` (a LangGraph graph) with memory |
| Benchmarking (retrieval and generation) | `evaluate.py`: Recall@k, MRR, execution accuracy, and RAGAS |
| Web interface | `app.py` (Streamlit) |
| Data versioning | DVC pipeline in `dvc.yaml`, data stored on DagsHub |

## Project structure

```
sql-analyst-agent/
├── app.py               web interface (Streamlit)
├── mcp_server.py        MCP tools: explain_schema, run_sql
├── evaluate.py          benchmark: retrieval + generation metrics
├── dvc.yaml             pipeline: download -> ingest -> evaluate
├── requirements.txt
├── .env.example         copy to .env and add your Groq key
└── src/
    ├── config.py        paths, model names, limits
    ├── download_data.py step 1: download + clean the dataset  -> data/bird/
    ├── ingest.py        step 2: tables -> documents -> FAISS  -> data/vectorstore/
    ├── retriever.py     search the relevant tables for a question
    ├── sql_tools.py     SQL safety check + read-only execution
    └── agent.py         the agent (Groq LLM + MCP tools + memory)
```

How a question flows: `app.py` → `agent.py` → (MCP) `explain_schema` → LLM writes SQL →
(MCP) `run_sql` → error? the LLM fixes it and retries → answer + SQL + sources.

---

## 1. Setup (everyone, once)

In Git Bash, with Python 3.11:

```bash
git clone https://github.com/<OWNER>/sql-analyst-agent.git
cd sql-analyst-agent
py -3.11 -m venv .venv
source .venv/Scripts/activate        # do this in every new terminal
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and paste your Groq API key (free, from https://console.groq.com/keys).

## 2. Data with DVC

**Why DVC:** one person downloads, cleans and indexes the data once, then pushes the result to
DagsHub. Everyone else gets the same files with `dvc pull`, without redoing the work. Git
stores the code and a small file (`dvc.lock`) that says which version of the data goes with it.

The pipeline (`dvc.yaml`) has three steps. `dvc repro` only reruns a step when its code or
input changed:

| Step | What it does | Output |
| --- | --- | --- |
| `download` | downloads BIRD Mini-Dev, cleans the description files (encodings, spaces), keeps the 11 databases and 500 questions | `data/bird/` |
| `ingest` | builds one document per table and stores the embeddings in FAISS | `data/vectorstore/` |
| `evaluate` | runs the benchmark (uses the Groq API) | `results/` |

### 2.1 First time: Ines sets it up and pushes the data

1. Push the code to a new GitHub repository (private or public, without README).
2. Create a DagsHub account at https://dagshub.com (sign in with GitHub), then
   **Create → Connect a repository → GitHub** and pick `sql-analyst-agent`.
3. In the project folder (venv active):

```bash
dvc init
dvc remote add -d origin https://dagshub.com/<DAGSHUB_USER>/sql-analyst-agent.dvc
dvc remote modify origin --local auth basic
dvc remote modify origin --local user <DAGSHUB_USER>
dvc remote modify origin --local password <DAGSHUB_TOKEN>

dvc repro ingest          # downloads + cleans the data, then builds the index

git add .
git commit -m "Add DVC pipeline and data"
git push
dvc push                  # uploads data/bird and data/vectorstore to DagsHub
```

`<DAGSHUB_TOKEN>` is in DagsHub → your profile → **Settings → Tokens**. The `--local`
settings stay on your laptop (never in Git), so each person uses their own token.

4. On DagsHub, open the repository → **Settings → Collaborators** and add Ouissem and Sarra.

If the Google Drive download fails ("too many users"), download the zip from the
[mini_dev page](https://github.com/bird-bench/mini_dev), save it as `data/minidev.zip`
and run `dvc repro ingest` again.

### 2.2 Ouissem and Sarra: get the data

After the setup of section 1:

```bash
dvc remote modify origin --local auth basic
dvc remote modify origin --local user <YOUR_DAGSHUB_USER>
dvc remote modify origin --local password <YOUR_DAGSHUB_TOKEN>
dvc pull
```

That's it: `data/bird/` and `data/vectorstore/` are now on your laptop.

### 2.3 Every time someone changes a step

The person who changed the code:

```bash
dvc repro                 # reruns only what changed
git add .
git commit -m "Describe the change"
git push
dvc push
```

Everyone else:

```bash
git pull
dvc pull
```

## 3. Run the app

```bash
streamlit run app.py
```

Pick a database in the sidebar and ask a question, for example on `formula_1`:
"Which 5 drivers scored the most points in 2013?", then "and for 2012?".

## 4. Evaluate

```bash
dvc repro evaluate        # or: python evaluate.py --n 20
dvc metrics show          # prints results/metrics.json
```

It samples 20 questions (30 % simple, 50 % moderate, 20 % challenging) and measures:

| Part | Metric | Meaning |
| --- | --- | --- |
| Retrieval | Recall@5 | share of the tables needed by the reference SQL that are in the top 5 |
| Retrieval | MRR | 1 / rank of the first needed table |
| Retrieval | RAGAS context recall | can the reference SQL be built from the retrieved schema? |
| Generation | Execution accuracy | the agent's SQL returns the same rows as the reference SQL (BIRD's metric) |
| Generation | RAGAS SQL equivalence | the LLM judge says both SQL queries are equivalent |
| Generation | RAGAS faithfulness | the answer is supported by the schema and the query result |

Results: `results/metrics.json` (summary, also by difficulty) and `results/eval_details.csv`
(one row per question). For reference, the BIRD authors report 24.4 % execution accuracy
for an 8B model and 45.8 % for gpt-4-turbo on this dataset.

## 5. Team roles

| Track | Owner | Files | Next step |
| --- | --- | --- | --- |
| A. Data and retrieval | Ines | `src/download_data.py`, `src/ingest.py`, `src/retriever.py`, DVC | set up DVC (section 2.1), check Recall@5 and MRR, improve the table documents if needed |
| B. Agent and safety | _(to assign)_ | `src/agent.py`, `src/sql_tools.py` | try 3 or 4 questions per database in the app, improve the prompt where the agent fails |
| C. MCP, interface, evaluation | _(to assign)_ | `mcp_server.py`, `app.py`, `evaluate.py` | run the evaluation, put the results in the report |

Git rule: one branch per change (`git switch -c feat/my-change`), small commits, a pull
request reviewed by a teammate before merging into `main`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ModuleNotFoundError` | activate the venv: `source .venv/Scripts/activate` |
| `dvc pull` asks for a password or says 401 | redo the three `dvc remote modify ... --local` lines with your DagsHub user and token |
| Groq "rate limit" errors | the free tier is limited: wait a minute, or run `python evaluate.py --n 10` |
| The app says a database file is missing | run `dvc pull` |
