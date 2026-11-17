"""STEP 3 - Split the questions of our 3 databases into dev and eval.

Run:    python -m evaluation.datasets.build_eval_set   (or: dvc repro build_eval_set)
Writes: data/questions/eval.jsonl  10 questions per database, mixed difficulty, FROZEN:
                                   used only for the final benchmark, never to tune anything
        data/questions/dev.jsonl   all other questions: to build and test the agent
Each question also gets `gold_tables`: the tables its reference SQL uses.
"""
import json
import random

import sqlglot
from sqlglot import exp

from data_engineering.config import DATABASES, EVAL_PER_DATABASE, QUESTIONS_DIR, RAW_DIR, SEED


def gold_tables(sql):
    tree = sqlglot.parse_one(sql, read="sqlite")
    ctes = {c.alias.lower() for c in tree.find_all(exp.CTE)}
    return sorted({t.name.lower() for t in tree.find_all(exp.Table) if t.name.lower() not in ctes})


def main():
    questions = json.loads((RAW_DIR / "questions.json").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    eval_set, dev_set = [], []
    for db_id in DATABASES:
        pool = [q for q in questions if q["db_id"] == db_id]
        rng.shuffle(pool)
        # take difficulties in turn so the eval set mixes simple, moderate and challenging
        by_level = {lvl: [q for q in pool if q["difficulty"] == lvl]
                    for lvl in ("simple", "moderate", "challenging")}
        chosen = []
        while len(chosen) < EVAL_PER_DATABASE and any(by_level.values()):
            for lvl in ("moderate", "simple", "challenging"):
                if by_level[lvl] and len(chosen) < EVAL_PER_DATABASE:
                    chosen.append(by_level[lvl].pop())
        eval_set += chosen
        dev_set += [q for q in pool if q not in chosen]

    QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in (("eval", eval_set), ("dev", dev_set)):
        with open(QUESTIONS_DIR / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for q in sorted(rows, key=lambda q: q["question_id"]):
                f.write(json.dumps({
                    "question_id": q["question_id"], "db_id": q["db_id"],
                    "difficulty": q["difficulty"], "question": q["question"],
                    "evidence": q.get("evidence", ""), "SQL": q["SQL"],
                    "gold_tables": gold_tables(q["SQL"]),
                }, ensure_ascii=False) + "\n")
    print(f"eval: {len(eval_set)} questions, dev: {len(dev_set)} questions -> {QUESTIONS_DIR}")


if __name__ == "__main__":
    main()
