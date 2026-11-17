"""The whole data pipeline on a tiny fake dataset: select -> clean -> eval set -> index -> API -> benchmark."""
import json

import pytest

from data_engineering import data_api, select_subset
from data_engineering.processing import clean
from data_engineering.retrieval import index
from evaluation.datasets import build_eval_set
from evaluation.retrieval import eval_retrieval


def run_pipeline():
    select_subset.main()
    clean.main()
    build_eval_set.main()
    index.main()


def test_select_keeps_only_our_databases(project):
    select_subset.main()
    raw = project / "raw"
    assert sorted(p.name for p in raw.iterdir() if p.is_dir()) == ["financial", "formula_1", "student_club"]
    questions = json.loads((raw / "questions.json").read_text(encoding="utf-8"))
    assert len(questions) == 36 and all(q["db_id"] != "toxicology" for q in questions)


def test_clean_documents_and_translations(project):
    select_subset.main()
    clean.main()
    docs = {d["id"]: d for d in map(json.loads, open(project / "processed" / "documents.jsonl", encoding="utf-8"))}
    assert len(docs) == 5                                    # one document per table
    account = docs["financial.account"]["text"]
    assert "how often statements are issued" in account      # spaces cleaned
    assert "'POPLATEK MESICNE' = monthly statement" in account  # Czech value translated
    assert "–" in docs["financial.loan"]["text"]        # Windows-1252 file read correctly
    assert docs["financial.account"]["metadata"]["source"] == "financial/database_description/account.csv"
    report = json.load(open(project / "processed" / "cleaning_report.json", encoding="utf-8"))
    assert "formula_1.races" in report["details"]["tables_without_description"]


def test_index_is_incremental(project, capsys):
    run_pipeline()
    index.main()
    assert "0 embedded, 5 unchanged" in capsys.readouterr().out


def test_data_api(project):
    run_pipeline()
    assert data_api.list_databases() == ["financial", "formula_1", "student_club"]
    hits = data_api.search_schema("monthly statement frequency of accounts", "financial", k=2)
    assert hits[0]["table"] == "account" and hits[0]["source"].endswith("account.csv")
    docs = data_api.get_retriever("formula_1", k=5).invoke("driver nationality")
    assert docs and all(d.metadata["db_id"] == "formula_1" for d in docs)
    assert "Table member" in data_api.get_schema_text("student_club")
    assert len(data_api.load_questions("eval")) == 30
    with pytest.raises(ValueError):
        data_api.search_schema("x", "toxicology")


def test_retrieval_benchmark(project):
    run_pipeline()
    eval_retrieval.main()
    metrics = json.load(open(project / "results" / "retrieval_metrics.json", encoding="utf-8"))
    assert metrics["questions"] == 30 and metrics["overall"]["mrr"] > 0.5
