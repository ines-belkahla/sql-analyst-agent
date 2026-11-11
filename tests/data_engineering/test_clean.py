import json
from data_engineering.processing import clean
from data_engineering import config


def test_helpers():
    assert clean.clean_text("  a\u00a0 b\n\nc ") == "a b c"
    assert clean.clean_text(None) == ""
    assert clean.humanize("birthDate") == "birth date"
    assert clean.humanize("T_Cell_count") == "t cell count"


def test_clean_pipeline(bird):
    clean.run()
    out = config.processed_dir()
    schemas = json.load(open(out / "schema.json"))
    report = json.load(open(out / "cleaning_report.json"))
    docs = [json.loads(l) for l in open(out / "documents.jsonl")]

    assert set(schemas) == {"formula_1", "financial"}
    drivers = next(t for t in schemas["formula_1"]["tables"] if t["name"] == "drivers")
    cols = {c["name"]: c for c in drivers["columns"]}
    assert cols["driverId"]["description"] == "unique id of the driver"        # whitespace normalised
    assert cols["forename"]["description"] == "first name of driver"           # newline removed
    assert cols["surname"]["description_source"] == "auto"                      # missing -> generated
    assert cols["surname"]["description"] == "surname"
    assert cols["nationality"]["samples"] == ["British", "German"]
    assert cols["driverId"]["is_pk"] and drivers["n_rows"] == 2

    results = next(t for t in schemas["formula_1"]["tables"] if t["name"] == "results")
    assert results["foreign_keys"] == [{"from": "driverId", "to_table": "drivers", "to_column": "driverId"}]

    races = next(t for t in schemas["formula_1"]["tables"] if t["name"] == "races")
    assert races["source"] == "sqlite schema"
    assert "formula_1.races" in report["details"]["tables_without_csv"]
    assert "formula_1.drivers.ghost" in report["details"]["csv_rows_without_column"]
    assert "formula_1.drivers.surname" in report["details"]["auto_descriptions"]

    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids))
    assert {"formula_1.drivers", "formula_1.drivers.surname", "formula_1.glossary.0", "formula_1.glossary.1"} <= set(ids)
    assert all(d["metadata"]["hash"] for d in docs)


def test_clean_is_deterministic(bird):
    clean.run(); a = (config.processed_dir() / "documents.jsonl").read_text()
    clean.run(); b = (config.processed_dir() / "documents.jsonl").read_text()
    assert a == b
