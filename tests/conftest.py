"""Builds a tiny fake BIRD package (2 databases, messy CSVs) and a fake embedding model."""
import json
import sqlite3
import zlib
import numpy as np
import pytest


@pytest.fixture
def bird(tmp_path, monkeypatch):
    raw = tmp_path / "raw" / "MINIDEV"
    f1 = raw / "dev_databases" / "formula_1"
    f2 = raw / "dev_databases" / "financial"
    for d in (f1, f2):
        (d / "database_description").mkdir(parents=True)
    c = sqlite3.connect(f1 / "formula_1.sqlite")
    c.execute("CREATE TABLE drivers(driverId INTEGER PRIMARY KEY, forename TEXT, surname TEXT, nationality TEXT)")
    c.execute("CREATE TABLE results(resultId INTEGER PRIMARY KEY, driverId INTEGER, points REAL, "
              "FOREIGN KEY(driverId) REFERENCES drivers(driverId))")
    c.execute("CREATE TABLE races(raceId INTEGER PRIMARY KEY, year INTEGER, name TEXT)")
    c.executemany("INSERT INTO drivers VALUES (?,?,?,?)", [(1, "Lewis", "Hamilton", "British"), (2, "Nico", "Rosberg", "German")])
    c.execute("INSERT INTO results VALUES (1, 1, 25.0)")
    c.commit(); c.close()
    # messy csv: BOM, padded header, trailing spaces, one column missing a description, orphan row
    (f1 / "database_description" / "drivers.csv").write_text(
        "\ufefforiginal_column_name, column_name ,column_description,data_format,value_description\n"
        "driverId,driver id,  unique id   of the driver ,integer,\n"
        'forename,first name,"first name\nof driver",text,\n'
        'nationality,,nationality of the driver,text,"e.g. British, German"\n'
        "ghost,ghost,not in db,text,\n", encoding="utf-8")
    (f1 / "database_description" / "results.csv").write_bytes(
        "original_column_name,column_name,column_description,data_format,value_description\n"
        "points,points,points scored in the race \u2013 championship,real,25 for a win\n".encode("latin-1", "replace"))
    c = sqlite3.connect(f2 / "financial.sqlite")
    c.execute("CREATE TABLE account(account_id INTEGER PRIMARY KEY, frequency TEXT, date TEXT)")
    c.execute("INSERT INTO account VALUES (1, 'POPLATEK MESICNE', '1993-01-01')")
    c.commit(); c.close()
    (f2 / "database_description" / "account.csv").write_text(
        "original_column_name,column_name,column_description,data_format,value_description\n"
        "frequency,frequency,frequency of statements issued,text,POPLATEK MESICNE = monthly issuance\n")
    gloss = tmp_path / "glossary"; gloss.mkdir()
    (gloss / "formula_1.md").write_text("# formula_1\n\nChampionship points: sum of points over a season.\n\nSecond definition.\n")
    for k, v in {"BIRD_DIR": raw.parent, "PROCESSED_DIR": tmp_path / "processed",
                 "INDEX_DIR": tmp_path / "index", "GLOSSARY_DIR": gloss}.items():
        monkeypatch.setenv(k, str(v))
    from data_engineering import schema_store
    schema_store._load.cache_clear()
    return tmp_path


class FakeModel:
    """Deterministic bag-of-words hashing embedder (no downloads)."""
    def encode(self, texts, normalize_embeddings=True, batch_size=64):
        out = np.zeros((len(texts), 256))
        for i, t in enumerate(texts):
            for w in "".join(ch.lower() if ch.isalnum() else " " for ch in t).split():
                out[i, zlib.crc32(w.encode()) % 256] += 1.0
        n = np.linalg.norm(out, axis=1, keepdims=True); n[n == 0] = 1
        return out / n


@pytest.fixture
def fake_embedder(monkeypatch):
    from data_engineering.retrieval import embeddings
    monkeypatch.setattr(embeddings, "_get", lambda: FakeModel())
    monkeypatch.setattr(embeddings, "_prefix", lambda: "")
