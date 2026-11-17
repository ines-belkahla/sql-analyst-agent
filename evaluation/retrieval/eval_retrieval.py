"""STEP 4 - Retrieval benchmark on the frozen eval questions (Qdrant must be running).

Run: python -m evaluation.retrieval.eval_retrieval   (or: dvc repro eval_retrieval)

For each question, the right tables are the ones its reference SQL uses (`gold_tables`).
  Recall@k    share of the right tables found in the top k
  Precision@k share of the top k that are right tables
  MRR         1 / rank of the first right table (1.0 = always first)
Writes evaluation/results/retrieval_metrics.json (summary) and retrieval_details.csv.
"""
import json

import pandas as pd

from data_engineering.config import RESULTS_DIR
from data_engineering.data_api import load_questions, search_schema

KS = [1, 3, 5]


def main():
    rows = []
    for q in load_questions("eval"):
        gold = set(q["gold_tables"])
        ranked = [hit["table"].lower() for hit in search_schema(q["question"], q["db_id"], k=max(KS))]
        row = {"question_id": q["question_id"], "db_id": q["db_id"], "difficulty": q["difficulty"],
               "gold_tables": ";".join(sorted(gold)), "retrieved": ";".join(ranked)}
        for k in KS:
            found = len(gold & set(ranked[:k]))
            row[f"recall@{k}"] = found / len(gold)
            row[f"precision@{k}"] = found / k
        row["mrr"] = next((1 / (i + 1) for i, t in enumerate(ranked) if t in gold), 0.0)
        rows.append(row)

    df = pd.DataFrame(rows)
    metric_cols = [c for c in df.columns if "@" in c or c == "mrr"]
    summary = {
        "questions": len(df),
        "overall": df[metric_cols].mean().round(3).to_dict(),
        "by_database": df.groupby("db_id")[metric_cols].mean().round(3).to_dict("index"),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS_DIR / "retrieval_details.csv", index=False)
    (RESULTS_DIR / "retrieval_metrics.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
