"""Benchmark the retrieval and the generation.

Run:  python evaluate.py          (20 questions)
      python evaluate.py --n 40   (more questions, slower)

Retrieval  (does the retriever find the tables the reference SQL uses?)
  - Recall@k : share of the needed tables found in the top k
  - MRR      : 1 / rank of the first needed table
  - RAGAS LLMContextRecall : can the reference SQL be built from the retrieved schema?
Generation (does the agent produce the right SQL and a faithful answer?)
  - Execution accuracy (EX) : same result rows as the reference SQL (the BIRD metric)
  - RAGAS LLMSQLEquivalence : is the generated SQL equivalent to the reference SQL?
  - RAGAS Faithfulness      : is the answer supported by the schema and the query result?

Results: results/metrics.json (summary) and results/eval_details.csv (one row per question).
"""

import argparse
import asyncio
import json
import uuid

import pandas as pd
import sqlglot
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from ragas import EvaluationDataset, RunConfig, evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import Faithfulness, LLMContextRecall, LLMSQLEquivalence

from src.agent import MCP_SERVERS, get_llm, run_agent
from src.config import QUESTIONS_FILE, RESULTS_DIR, TOP_K
from src.retriever import search_schema
from src.sql_tools import run_sql


def sample_questions(n, seed=42):
    """n questions with the dataset's difficulty mix (30% simple, 50% moderate, 20% challenging)."""
    questions = pd.DataFrame(json.loads(QUESTIONS_FILE.read_text(encoding="utf-8")))
    shares = {"simple": 0.3, "moderate": 0.5, "challenging": 0.2}
    parts = [questions[questions.difficulty == level].sample(round(n * share), random_state=seed)
             for level, share in shares.items()]
    return pd.concat(parts).to_dict("records")


def gold_tables(sql):
    """Tables used by the reference SQL (the right answer for the retriever)."""
    return {t.name.lower() for t in sqlglot.parse_one(sql, read="sqlite").find_all(sqlglot.exp.Table)}


async def run_agent_on_all(questions):
    """Run the agent on every question, reusing one MCP server for speed."""
    outputs = []
    client = MultiServerMCPClient(MCP_SERVERS)
    async with client.session("sql") as session:
        tools = await load_mcp_tools(session)
        for i, q in enumerate(questions, 1):
            text = q["question"] + (f"\nHint: {q['evidence']}" if q["evidence"] else "")
            try:
                out = await run_agent(tools, text, q["db_id"], str(uuid.uuid4()), InMemorySaver())
            except Exception as error:  # e.g. API rate limit: count it as a failure
                out = {"answer": f"ERROR: {error}", "sql": None, "rows": [], "contexts": []}
            print(f"  {i}/{len(questions)} done")
            outputs.append(out)
    return outputs


def main(n):
    questions = sample_questions(n)
    rows = []

    # ---------------- 1. Retrieval ----------------
    print("Retrieval...")
    for q in questions:
        needed = gold_tables(q["SQL"])
        docs = search_schema(q["db_id"], q["question"], k=TOP_K)
        found = [d.metadata["table"].lower() for d in docs]
        first_hit = next((i for i, t in enumerate(found, 1) if t in needed), None)
        rows.append({
            "question_id": q["question_id"], "db_id": q["db_id"], "difficulty": q["difficulty"],
            "question": q["question"], "gold_sql": q["SQL"],
            "needed_tables": sorted(needed), "retrieved_tables": found,
            f"recall@{TOP_K}": len(needed & set(found)) / len(needed),
            "mrr": 1 / first_hit if first_hit else 0.0,
            "retrieved_contexts": [d.page_content for d in docs],
        })

    # ---------------- 2. Generation ----------------
    print("Generation (agent)...")
    outputs = asyncio.run(run_agent_on_all(questions))
    for row, out in zip(rows, outputs, strict=True):
        gold = run_sql(row["db_id"], row["gold_sql"], timeout=60)
        pred = run_sql(row["db_id"], out["sql"], timeout=60) if out["sql"] else {"ok": False}
        # same rows, ignoring order and duplicates (how BIRD compares results)
        same = pred["ok"] and gold["ok"] and set(map(tuple, pred["rows"])) == set(map(tuple, gold["rows"]))
        row.update(predicted_sql=out["sql"] or "", answer=out["answer"],
                   execution_accuracy=float(same),
                   agent_contexts=out["contexts"] + [f"Query result: {out['rows'][:20]}"])

    # ---------------- 3. RAGAS ----------------
    print("RAGAS (LLM as a judge)...")
    judge = LangchainLLMWrapper(get_llm())
    config = RunConfig(max_workers=2, timeout=180)  # slow and steady: free API rate limits

    retrieval_data = EvaluationDataset.from_list([
        {"user_input": r["question"], "retrieved_contexts": r["retrieved_contexts"],
         "reference": r["gold_sql"]} for r in rows])
    sql_data = EvaluationDataset.from_list([
        {"response": r["predicted_sql"], "reference": r["gold_sql"],
         "reference_contexts": r["retrieved_contexts"]} for r in rows])
    answer_data = EvaluationDataset.from_list([
        {"user_input": r["question"], "response": r["answer"],
         "retrieved_contexts": r["agent_contexts"]} for r in rows])

    scores = {}
    for name, dataset, metric in [
        ("context_recall", retrieval_data, LLMContextRecall()),
        ("sql_equivalence", sql_data, LLMSQLEquivalence()),
        ("faithfulness", answer_data, Faithfulness()),
    ]:
        result = evaluate(dataset, metrics=[metric], llm=judge, run_config=config).to_pandas()
        scores[name] = result.iloc[:, -1].tolist()

    # ---------------- 4. Save ----------------
    df = pd.DataFrame(rows).drop(columns=["retrieved_contexts", "agent_contexts"])
    for name, values in scores.items():
        df[name] = values
    df.loc[df.predicted_sql == "", "sql_equivalence"] = 0.0  # no SQL produced = wrong
    metric_cols = [f"recall@{TOP_K}", "mrr", "context_recall",
                   "execution_accuracy", "sql_equivalence", "faithfulness"]

    summary = {
        "questions": len(df),
        "overall": df[metric_cols].mean().round(3).to_dict(),
        "by_difficulty": df.groupby("difficulty")[metric_cols].mean().round(3).to_dict("index"),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(RESULTS_DIR / "eval_details.csv", index=False)
    (RESULTS_DIR / "metrics.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20, help="number of questions")
    main(parser.parse_args().n)
