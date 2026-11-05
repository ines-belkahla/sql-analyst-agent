"""Step 2: turn every table into a document and store it in the vector database.

Run:  python -m src.ingest   (or: dvc repro ingest)

One document per table. Its text lists the columns with their type and their
description, the primary keys and the foreign keys. Its metadata (db_id, table,
source) lets us filter by database and cite the description file in the answers.
"""

import sqlite3

import pandas as pd
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import (
    DESCRIPTIONS_FILE,
    EMBEDDING_MODEL,
    VECTOR_STORE_DIR,
    database_path,
    list_databases,
)


def table_documents(db_id, descriptions):
    conn = sqlite3.connect(f"file:{database_path(db_id).as_posix()}?mode=ro", uri=True)
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )]

    documents = []
    for table in tables:
        columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        foreign_keys = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        desc = descriptions[
            (descriptions.db_id == db_id) & (descriptions.table.str.lower() == table.lower())
        ]

        lines = [f"Table {table} (database {db_id})", "Columns:"]
        for _, name, col_type, _, _, is_pk in columns:
            row = desc[desc.column.str.lower() == name.lower()]
            text = f"- {name} ({col_type or 'ANY'}{', primary key' if is_pk else ''})"
            if not row.empty:
                r = row.iloc[0]
                text += f": {r.description or r.column_name}"
                if r.value_description:
                    text += f". Values: {r.value_description}"
            lines.append(text)
        for fk in foreign_keys:
            lines.append(f"Foreign key: {table}.{fk[3]} -> {fk[2]}.{fk[4]}")

        source = desc.source.iloc[0] if not desc.empty else f"{db_id}/{db_id}.sqlite"
        documents.append(Document(
            page_content="\n".join(lines),
            metadata={"db_id": db_id, "table": table, "source": source},
        ))
    conn.close()
    return documents


if __name__ == "__main__":
    descriptions = pd.read_csv(DESCRIPTIONS_FILE, dtype=str, keep_default_na=False)

    documents = []
    for db_id in list_databases():
        docs = table_documents(db_id, descriptions)
        print(f"{db_id}: {len(docs)} tables")
        documents.extend(docs)

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vector_store = FAISS.from_documents(documents, embeddings)
    vector_store.save_local(str(VECTOR_STORE_DIR))
    print(f"{len(documents)} documents stored in {VECTOR_STORE_DIR}")
