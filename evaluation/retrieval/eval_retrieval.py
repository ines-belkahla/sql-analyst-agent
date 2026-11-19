"""STEP 4 - Retrieval benchmark (Qdrant must be running).

Run:
  python -m evaluation.retrieval.eval_retrieval                      # eval, no rerank (what DVC runs)
  python -m evaluation.retrieval.eval_retrieval --split dev          # tune on dev
  python -m evaluation.retrieval.eval_retrieval --split dev --rerank # dev with the reranker
  python -m evaluation.retrieval.eval_retrieval --split dev --fk     # add the linking tables (foreign keys)
  python -m evaluation.retrieval.eval_retrieval --rerank             # FINAL numbers on eval (do it once)

For each question, the right tables are the ones its reference SQL uses (`gold_tables`).
  Recall@k    share of the right tables found in the top k
  Precision@k share of the top k that are right tables
  MRR         1 / rank of the first right table (1.0 = always first)
  tables@k    how many tables the LLM would receive (k, or more with --fk)
With --fk, "top k" means the k best tables PLUS the linking tables added for them, so recall can only go up
(and tables@k and precision tell you what it costs).

Output files: the default run (eval, no rerank) writes retrieval_metrics.json and
retrieval_details.csv, as before (DVC metric). Every other run writes
retrieval_metrics_<split>[_rerank][_fk].json and retrieval_details_<split>[_rerank][_fk].csv.
"""
import argparse
import json
import sys

import pandas as pd

from data_engineering.config import FETCH_K, RESULTS_DIR
from data_engineering.data_api import load_questions, search_schema
from data_engineering.retrieval.fk_expand import expand_with_fk

KS = [1, 3, 5]


def evaluate(split, rerank, fetch_k, fk=False, min_links=2, max_extra=3):
    rows = []
    for q in load_questions(split):
        gold = set(q["gold_tables"])
        hits = search_schema(q["question"], q["db_id"], k=max(KS), rerank=rerank, fetch_k=fetch_k)
        ranked = [hit["table"].lower() for hit in hits]
        row = {"question_id": q["question_id"], "db_id": q["db_id"], "difficulty": q["difficulty"],
               "gold_tables": ";".join(sorted(gold)), "retrieved": ";".join(ranked)}
        for k in KS:
            context = ranked[:k]                      # the tables the LLM would receive
            if fk:
                extra = expand_with_fk(q["db_id"], hits[:k], min_links, max_extra)
                context = context + [e["table"].lower() for e in extra]
            found = len(gold & set(context))
            row[f"recall@{k}"] = found / len(gold)
            row[f"precision@{k}"] = found / len(context)
            row[f"tables@{k}"] = len(context)
        row["mrr"] = next((1 / (i + 1) for i, t in enumerate(ranked) if t in gold), 0.0)
        rows.append(row)
    return pd.DataFrame(rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "eval"], default="eval",
                        help="dev to tune, eval only for the final numbers")
    parser.add_argument("--rerank", action="store_true", help="rerank Qdrant candidates with a cross-encoder")
    parser.add_argument("--fetch-k", type=int, default=FETCH_K,
                        help="candidates taken from Qdrant before reranking")
    parser.add_argument("--fk", action="store_true", help="add the tables that link the retrieved ones (foreign keys)")
    parser.add_argument("--min-links", type=int, default=2,
                        help="with --fk: add a table only if linked to at least this many retrieved tables")
    parser.add_argument("--max-extra", type=int, default=3, help="with --fk: add at most this many tables")
    args = parser.parse_args([] if argv is None else argv)  # no args: eval, no rerank

    df = evaluate(args.split, args.rerank, args.fetch_k, args.fk, args.min_links, args.max_extra)
    metric_cols = [c for c in df.columns if "@" in c or c == "mrr"]
    summary = {
        "split": args.split,
        "rerank": args.rerank,
        "fetch_k": args.fetch_k if args.rerank else None,
        "fk": args.fk,
        "min_links": args.min_links if args.fk else None,
        "max_extra": args.max_extra if args.fk else None,
        "questions": len(df),
        "overall": df[metric_cols].mean().round(3).to_dict(),
        "by_database": df.groupby("db_id")[metric_cols].mean().round(3).to_dict("index"),
    }

    default_run = args.split == "eval" and not args.rerank and not args.fk
    suffix = "" if default_run else f"_{args.split}" + ("_rerank" if args.rerank else "") + ("_fk" if args.fk else "")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS_DIR / f"retrieval_details{suffix}.csv", index=False)
    (RESULTS_DIR / f"retrieval_metrics{suffix}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
