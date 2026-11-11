"""Builds evaluation/data/eval_set.jsonl: N Mini-Dev questions stratified by difficulty and spread over databases,
with the gold tables extracted from the reference SQL. Owner: Person A. Used by A (retrieval eval) and B (SQL eval).
Run: python -m evaluation.datasets.build_eval_set
"""
import json
import random
from collections import defaultdict
import sqlglot
from sqlglot import exp
from data_engineering import config

TARGET = {"simple": 0.30, "moderate": 0.50, "challenging": 0.20}


def gold_tables(sql: str) -> list[str]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    ctes = {c.alias.lower() for c in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table) if t.name.lower() not in ctes})


def run() -> None:
    p = config.params()["eval"]
    data = json.load(open(config.questions_file(), encoding="utf-8"))
    rng = random.Random(p["seed"])
    by_diff = defaultdict(list)
    for d in data:
        by_diff[d["difficulty"]].append(d)
    picked = []
    for diff, share in TARGET.items():
        pool = by_diff[diff][:]
        rng.shuffle(pool)
        by_db = defaultdict(list)
        for d in pool:
            by_db[d["db_id"]].append(d)
        want, chosen = round(p["n_questions"] * share), []
        while len(chosen) < want and any(by_db.values()):
            for db in sorted(by_db):
                if by_db[db] and len(chosen) < want:
                    chosen.append(by_db[db].pop())
        picked += chosen
    out = config.ROOT / "evaluation" / "data" / "eval_set.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for d in sorted(picked, key=lambda x: x["question_id"]):
            f.write(json.dumps({"id": d["question_id"], "db_id": d["db_id"], "question": d["question"],
                                "evidence": d.get("evidence", ""), "gold_sql": d["SQL"],
                                "difficulty": d["difficulty"], "gold_tables": gold_tables(d["SQL"])},
                               ensure_ascii=False) + "\n")
    print(f"wrote {len(picked)} questions, {len({d['db_id'] for d in picked})} databases -> {out}")


if __name__ == "__main__":
    run()
