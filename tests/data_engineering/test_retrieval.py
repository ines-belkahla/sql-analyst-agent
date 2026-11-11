import pytest
from data_engineering.processing import clean
from data_engineering.retrieval import index, search, context


@pytest.fixture
def built(bird, fake_embedder):
    clean.run()
    return index.run()


def test_index_incremental(built):
    assert built["embedded"] == built["documents"] == built["index_size"]
    again = index.run()
    assert again["embedded"] == 0 and again["deleted"] == 0


def test_search_filters_and_ranks(built):
    hits = search.search("nationality of the driver", "formula_1", k=5)
    assert all(h.db_id == "formula_1" for h in hits)
    assert "drivers" in search.rank_tables(hits)[:2]
    assert all(h.source for h in hits)                      # every hit is citable


def test_route_db(built):
    assert search.route_db("monthly issuance frequency of account statements") == "financial"
    assert search.route_db("championship points of the driver") == "formula_1"


def test_context(built):
    ctx = context.build_schema_context("points scored by driver nationality", "formula_1", k=12)
    assert ctx.db_id == "formula_1"
    assert "TABLE drivers" in ctx.text and "FK driverId -> drivers.driverId" in ctx.text
    assert "results" in ctx.tables and "drivers" in ctx.tables      # FK expansion keeps join path
    assert ctx.citations and ctx.to_dict()["db_id"] == "formula_1"


def test_context_auto_routes(built):
    assert context.build_schema_context("monthly issuance frequency of account statements").db_id == "financial"
