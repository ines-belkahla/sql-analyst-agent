"""RETRIEVAL BENCHMARK. Owner: Person A.   Run: python -m evaluation.retrieval.eval_retrieval
Metrics (gold tables come from the reference SQL):
  given_db   : Recall@3/5/10 and MRR when the database is known
  routed_db  : same, but the agent must first find the database (also reports routing accuracy)
  context    : table recall of the final schema context handed to the SQL generator (what B actually uses)
"""
import json
from pathlib import Path
import pandas as pd
from data_engineering.retrieval.search import search, rank_tables, route_db
from data_engineering.retrieval.context import build_schema_context

HERE = Path(__file__).parent
KS = [3, 5, 10]


def main():
    rows = [json.loads(l) for l in open(HERE.parent / "data" / "eval_set.jsonl", encoding="utf-8")]
    res = []
    for r in rows:
        gold = {t.lower() for t in r["gold_tables"]}
        for mode in ("given_db", "routed_db"):
            db = r["db_id"] if mode == "given_db" else route_db(r["question"])
            ranked = [t.lower() for t in rank_tables(search(r["question"], db, 40))] if db == r["db_id"] else []
            rec = {f"recall@{k}": len(gold & set(ranked[:k])) / len(gold) for k in KS}
            mrr = next((1 / (i + 1) for i, t in enumerate(ranked) if t in gold), 0.0)
            ctx = build_schema_context(r["question"], r["db_id"] if mode == "given_db" else None)
            ctx_rec = len(gold & {t.lower() for t in ctx.tables}) / len(gold) if ctx.db_id == r["db_id"] else 0.0
            res.append({"mode": mode, "difficulty": r["difficulty"], "db_correct": int(db == r["db_id"]),
                        "mrr": mrr, "context_recall": ctx_rec, **rec})
    df = pd.DataFrame(res)
    print(df.groupby("mode").mean(numeric_only=True).round(3).T)
    print(df.groupby(["mode", "difficulty"]).mean(numeric_only=True).round(3))
    out = HERE.parent / "results"
    out.mkdir(exist_ok=True)
    df.to_csv(out / "retrieval_details.csv", index=False)
    metrics = {f"{mode}.{c}": round(v, 4) for mode, g in df.groupby("mode") for c, v in g.mean(numeric_only=True).items()}
    (out / "retrieval_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
