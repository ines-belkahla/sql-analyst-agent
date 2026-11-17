"""STEP 1 - Clean the BIRD documentation and turn every table into one document.

Run:   python -m data_engineering.processing.clean   (or: dvc repro clean)
Reads: data/raw/<db>/<db>.sqlite and data/raw/<db>/database_description/*.csv
Writes data/processed/documents.jsonl      one document per table (the RAG documents)
       data/processed/schema.json          the cleaned schema, used by data_api.get_schema_text()
       data/processed/cleaning_report.json what was fixed or is missing

The database VALUES are never changed: BIRD's reference SQL uses them as stored
(e.g. 'POPLATEK MESICNE'). Czech values are translated in the documents instead.
"""
import csv
import hashlib
import io
import json
import re
import sqlite3

from data_engineering.config import DATABASES, PROCESSED_DIR, RAW_DIR, database_path

# English meaning of the Czech codes stored in the `financial` database
# (from the documentation of the original PKDD'99 Czech bank dataset).
CZECH_TERMS = {
    "POPLATEK MESICNE": "monthly statement",
    "POPLATEK TYDNE": "weekly statement",
    "POPLATEK PO OBRATU": "statement after each transaction",
    "PRIJEM": "credit (money in)",
    "VYDAJ": "withdrawal (money out)",
    "VYBER": "cash withdrawal",
    "VYBER KARTOU": "credit card withdrawal",
    "VKLAD": "cash deposit",
    "PREVOD Z UCTU": "collection from another bank",
    "PREVOD NA UCET": "transfer to another bank",
    "POJISTNE": "insurance payment",
    "SLUZBY": "payment for statement",
    "UROK": "interest credited",
    "SANKC. UROK": "penalty interest (negative balance)",
    "SIPO": "household payment",
    "DUCHOD": "old-age pension",
    "UVER": "loan payment",
    "DISPONENT": "authorized user (not the owner)",
}
MAX_CATEGORIES = 20  # a text column with at most 20 distinct values is a category


def clean_text(text):
    """Remove extra spaces, line breaks and invisible characters."""
    text = str(text or "").replace("﻿", "").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def read_csv(path):
    """BIRD description files use different encodings: try them in order."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        row = {clean_text(k).lower(): clean_text(v) for k, v in row.items() if k}
        if row.get("original_column_name"):
            rows.append(row)
    return rows


def categories(conn, table, column):
    """Distinct values of a text column, or [] if it has too many to be a category."""
    rows = conn.execute(
        f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL '
        f"LIMIT {MAX_CATEGORIES + 1}"
    ).fetchall()
    values = [str(r[0]).strip() for r in rows if isinstance(r[0], str) and r[0].strip()]
    return values if len(values) <= MAX_CATEGORIES else []


def clean_database(db_id, report):
    conn = sqlite3.connect(f"file:{database_path(db_id).as_posix()}?mode=ro", uri=True)
    csv_files = {p.stem.strip().lower(): p for p in (RAW_DIR / db_id / "database_description").glob("*.csv")}
    tables = []
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for table in names:
        csv_file = csv_files.get(table.lower())
        described = {r["original_column_name"].lower(): r for r in read_csv(csv_file)} if csv_file else {}
        if not csv_file:
            report["tables_without_description"].append(f"{db_id}.{table}")

        columns = []
        for _, name, col_type, _, _, is_pk in conn.execute(f'PRAGMA table_info("{table}")'):
            row = described.get(name.lower(), {})
            description = row.get("column_description") or row.get("column_name") or ""
            if not description:
                report["columns_without_description"].append(f"{db_id}.{table}.{name}")

            values = categories(conn, table, name)  # numbers and long free text give []
            translations = {v: CZECH_TERMS[v] for v in values if v in CZECH_TERMS}
            if db_id == "financial":
                for v in values:
                    if v not in CZECH_TERMS and v.isupper() and len(v) > 3:
                        report["values_without_translation"].append(f"{db_id}.{table}.{name} = {v}")

            columns.append({
                "name": name,
                "type": col_type or "",
                "primary_key": bool(is_pk),
                "description": description,
                "value_description": row.get("value_description", ""),
                "values": values,
                "translations": translations,
            })

        foreign_keys = [{"column": r[3], "ref_table": r[2], "ref_column": r[4]}
                        for r in conn.execute(f'PRAGMA foreign_key_list("{table}")')]
        tables.append({
            "name": table,
            "rows": conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0],
            "source": f"{db_id}/database_description/{csv_file.name}" if csv_file else f"{db_id}/{db_id}.sqlite",
            "columns": columns,
            "foreign_keys": foreign_keys,
        })
    conn.close()
    return tables


def table_document(db_id, table):
    """The text that gets embedded, plus the metadata used for filtering and citations."""
    lines = [f"Table {table['name']} in database {db_id} ({table['rows']} rows).", "Columns:"]
    for c in table["columns"]:
        line = f"- {c['name']} ({c['type'] or 'ANY'}{', primary key' if c['primary_key'] else ''})"
        if c["description"]:
            line += f": {c['description']}"
        if c["value_description"]:
            line += f". {c['value_description'][:300]}"
        if c["translations"]:
            line += ". Values: " + ", ".join(f"'{k}' = {v}" for k, v in c["translations"].items())
        elif c["values"]:
            line += ". Values: " + ", ".join(f"'{v}'" for v in c["values"][:8])
        lines.append(line)
    for fk in table["foreign_keys"]:
        lines.append(f"Foreign key: {table['name']}.{fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")
    text = "\n".join(lines)
    return {
        "id": f"{db_id}.{table['name']}",
        "text": text,
        "metadata": {
            "db_id": db_id,
            "table": table["name"],
            "source": table["source"],
            "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        },
    }


def main():
    report = {"tables_without_description": [], "columns_without_description": [],
              "values_without_translation": []}
    schema = {db_id: clean_database(db_id, report) for db_id in DATABASES}
    documents = [table_document(db_id, t) for db_id, tables in schema.items() for t in tables]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    (PROCESSED_DIR / "schema.json").write_text(json.dumps(schema, indent=1, ensure_ascii=False), encoding="utf-8")
    with open(PROCESSED_DIR / "documents.jsonl", "w", encoding="utf-8") as f:
        for doc in documents:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    report["values_without_translation"] = sorted(set(report["values_without_translation"]))
    summary = {"databases": len(schema), "documents": len(documents),
               **{k: len(v) for k, v in report.items()}}
    (PROCESSED_DIR / "cleaning_report.json").write_text(
        json.dumps({"summary": summary, "details": report}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
