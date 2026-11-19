"""The whole data pipeline on a tiny fake dataset: select -> clean -> eval set -> index -> API -> benchmark."""
import json

import pytest

from data_engineering import data_api, select_subset
from data_engineering.processing import clean
from data_engineering.retrieval import fk_expand, index, rerank
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


class FakeReranker:
    """Stands in for the cross-encoder: scores a (question, table text) pair by shared words."""
    def predict(self, pairs):
        return [float(len(set(q.lower().split()) & set(t.lower().split()))) for q, t in pairs]


def test_search_with_rerank(project, monkeypatch):
    run_pipeline()
    monkeypatch.setattr(rerank, "get_reranker", lambda: FakeReranker())
    hits = data_api.search_schema("monthly statement frequency of accounts", "financial",
                                  k=2, rerank=True, fetch_k=5)
    assert len(hits) == 2
    assert all({"table", "text", "source", "score", "vector_score"} <= set(h) for h in hits)
    assert hits[0]["score"] >= hits[1]["score"]


def test_retrieval_benchmark_dev_with_rerank(project, monkeypatch):
    run_pipeline()
    monkeypatch.setattr(rerank, "get_reranker", lambda: FakeReranker())
    eval_retrieval.main(["--split", "dev", "--rerank"])
    metrics = json.load(open(project / "results" / "retrieval_metrics_dev_rerank.json", encoding="utf-8"))
    assert metrics["split"] == "dev" and metrics["rerank"] is True
    assert not (project / "results" / "retrieval_metrics.json").exists()  # DVC metric left untouched


def test_pick_bridge_tables():
    graph = {"drivers": {"results"}, "races": {"results"}, "status": {"results"},
             "results": {"drivers", "races", "status"}}
    assert fk_expand.pick_bridge_tables(graph, ["drivers", "races"]) == ["results"]            # bridge
    assert fk_expand.pick_bridge_tables(graph, ["drivers"], min_links=2) == []                 # not a bridge
    assert fk_expand.pick_bridge_tables(graph, ["Results"], min_links=1, max_extra=2) == ["drivers", "races"]
    assert fk_expand.pick_bridge_tables(graph, ["results", "drivers"], min_links=1) == ["races", "status"]


def test_fk_graph_and_expansion(project):
    run_pipeline()
    assert fk_expand.get_fk_graph("financial") == {"account": {"loan"}, "loan": {"account"}}
    extra = fk_expand.expand_with_fk("financial", [{"table": "loan"}], min_links=1)
    assert [e["table"] for e in extra] == ["account"] and extra[0]["via"] == "fk" and extra[0]["text"]
    assert fk_expand.expand_with_fk("financial", [{"table": "loan"}], min_links=2) == []
    hits = data_api.search_schema("approved loan amount", "financial", k=1, expand_fk=True, min_links=1)
    assert {h["table"] for h in hits} == {"account", "loan"} and hits[-1]["via"] == "fk"


def test_retrieval_benchmark_with_fk(project):
    run_pipeline()
    eval_retrieval.main(["--split", "dev"])
    eval_retrieval.main(["--split", "dev", "--fk", "--min-links", "1"])
    read = lambda name: json.load(open(project / "results" / name, encoding="utf-8"))
    plain, fk = read("retrieval_metrics_dev.json"), read("retrieval_metrics_dev_fk.json")
    assert fk["fk"] is True and "tables@3" in fk["overall"]
    assert fk["overall"]["recall@3"] >= plain["overall"]["recall@3"]       # adding tables can only help recall
    assert fk["overall"]["tables@3"] >= plain["overall"]["tables@3"]
