"""Test setup: a tiny fake BIRD download, an in-memory Qdrant and an offline embedding model.
The tests need no Docker, no internet and no real dataset."""
import json
import sqlite3
import zlib

import numpy as np
import pytest
from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from data_engineering import config, data_api, select_subset
from data_engineering.processing import clean
from data_engineering.retrieval import index
from evaluation.datasets import build_eval_set
from evaluation.retrieval import eval_retrieval

HEADER = "original_column_name,column_name,column_description,data_format,value_description\n"


class WordEmbeddings(Embeddings):
    """Offline stand-in for the real model: similar words give similar vectors."""

    def _vec(self, text):
        v = np.zeros(128)
        for w in "".join(c.lower() if c.isalnum() else " " for c in text).split():
            v[zlib.crc32(w.encode()) % 128] += 1
        return (v / (np.linalg.norm(v) or 1)).tolist()

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def make_db(folder, db_id, sql, csvs):
    target = folder / db_id
    (target / "database_description").mkdir(parents=True)
    conn = sqlite3.connect(target / f"{db_id}.sqlite")
    conn.executescript(sql)
    conn.close()
    for name, (encoding, text) in csvs.items():
        (target / "database_description" / name).write_bytes(text.encode(encoding))


@pytest.fixture
def project(tmp_path, monkeypatch):
    dev = tmp_path / "download" / "minidev" / "MINIDEV" / "dev_databases"
    make_db(dev, "financial",
            "CREATE TABLE account(account_id INTEGER PRIMARY KEY, frequency TEXT, date TEXT);"
            "INSERT INTO account VALUES (1,'POPLATEK MESICNE','1995-03-24'),(2,'POPLATEK TYDNE','1996-01-01');"
            "CREATE TABLE loan(loan_id INTEGER PRIMARY KEY, account_id INTEGER REFERENCES account(account_id),"
            " amount INTEGER, status TEXT);"
            "INSERT INTO loan VALUES (1,1,80000,'A');",
            {"account.csv": ("utf-8-sig", HEADER + "account_id,account id,the id of the account,integer,\n"
                             "frequency, frequency ,  how often statements   are issued ,text,\n"),
             "loan.csv": ("cp1252", HEADER + "amount,amount,approved loan amount – in CZK,integer,\n"
                          "status,status,repayment status,text,A = contract finished\n")})
    make_db(dev, "formula_1",
            "CREATE TABLE drivers(driverId INTEGER PRIMARY KEY, surname TEXT, nationality TEXT);"
            "INSERT INTO drivers VALUES (1,'Hamilton','British'),(2,'Vettel','German');"
            "CREATE TABLE races(raceId INTEGER PRIMARY KEY, year INTEGER, name TEXT);",
            {"drivers.csv": ("utf-8", HEADER + "nationality,nationality,nationality of the driver,text,\n")})
    make_db(dev, "student_club",
            "CREATE TABLE member(member_id TEXT PRIMARY KEY, first_name TEXT, major TEXT);",
            {"member.csv": ("utf-8", HEADER + "first_name,first name,first name of the member,text,\n")})
    make_db(dev, "toxicology", "CREATE TABLE atom(atom_id TEXT);", {})  # not kept
    (tmp_path / "download" / "__MACOSX").mkdir()                         # junk must be ignored

    questions = []
    for i in range(36):
        db_id = ["financial", "formula_1", "student_club"][i % 3]
        sql = {"financial": "SELECT COUNT(*) FROM account WHERE frequency = 'POPLATEK MESICNE'",
               "formula_1": "SELECT surname FROM drivers WHERE nationality = 'German'",
               "student_club": "SELECT first_name FROM member"}[db_id]
        question = {"financial": "How many accounts have a monthly statement frequency?",
                    "formula_1": "Which drivers have German nationality?",
                    "student_club": "List the first name of every member."}[db_id]
        questions.append({"question_id": i, "db_id": db_id, "question": question, "evidence": "",
                          "SQL": sql, "difficulty": ["simple", "moderate", "challenging"][i % 3]})
    questions.append({"question_id": 99, "db_id": "toxicology", "question": "q", "evidence": "",
                      "SQL": "SELECT 1", "difficulty": "simple"})
    (dev.parent / "mini_dev_sqlite.json").write_text(json.dumps(questions), encoding="utf-8")

    # point every module at the temporary folders
    paths = {"DOWNLOAD_DIR": tmp_path / "download", "RAW_DIR": tmp_path / "raw",
             "PROCESSED_DIR": tmp_path / "processed", "QUESTIONS_DIR": tmp_path / "questions",
             "RESULTS_DIR": tmp_path / "results"}
    for module in (config, select_subset, clean, data_api, index, build_eval_set, eval_retrieval):
        for name, value in paths.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value)

    client = QdrantClient(location=":memory:")
    monkeypatch.setattr(data_api, "get_client", lambda: client)
    monkeypatch.setattr(data_api, "get_embeddings", lambda: WordEmbeddings())
    monkeypatch.setattr(index, "get_client", lambda: client)
    monkeypatch.setattr(index, "get_embeddings", lambda: WordEmbeddings())
    return tmp_path
