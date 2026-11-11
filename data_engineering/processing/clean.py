"""STEP 1 - DATA CLEANING. Owner: Person A.

Reads   data/raw/**/dev_databases/<db>/{<db>.sqlite, database_description/*.csv}  and  data/glossary/*.md
Writes  data/processed/schema.json           clean structured schema (tables, columns, keys, descriptions, samples)
        data/processed/documents.jsonl       one retrieval document per table / column / glossary paragraph
        data/processed/cleaning_report.json  what was fixed or missing (for the report)

Run: python -m data_engineering.processing.clean
"""
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from data_engineering import config

CSV_KEYS = ("original_column_name", "column_name", "column_description", "data_format", "value_description")


# ---------- text helpers ----------
def clean_text(s) -> str:
    """Normalise whitespace / odd characters; None -> ''."""
    if s is None:
        return ""
    s = str(s).replace("\u00a0", " ").replace("\ufeff", "").replace("\r", "\n")
    return re.sub(r"\s+", " ", s).strip()


def humanize(name: str) -> str:
    """'T_Cell_count' / 'birthDate' / 'cdsCode' -> 'cell count' style words."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return re.sub(r"[_\s]+", " ", s).strip().lower()


def read_description_csv(path: Path) -> tuple[list[dict], str]:
    """Return (rows with normalised keys, encoding used). Tries utf-8 then latin-1."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as f:
                rows = []
                for r in csv.DictReader(f):
                    rows.append({(k or "").strip().lower(): clean_text(v) for k, v in r.items()})
                return rows, enc
        except UnicodeDecodeError:
            continue
    return [], "unreadable"


# ---------- sqlite helpers ----------
def _ro(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    c.text_factory = lambda b: b.decode("utf-8", errors="replace")
    return c


def _samples(conn, table: str, col: str, n: int, max_chars: int) -> list[str]:
    try:
        rows = conn.execute(
            f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT {int(n)}').fetchall()
    except sqlite3.Error:
        return []
    out = []
    for (v,) in rows:
        if isinstance(v, bytes):
            continue
        t = clean_text(v)
        out.append(t[:max_chars] + ("..." if len(t) > max_chars else ""))
    return out


# ---------- main cleaning ----------
def clean_database(db_id: str, p: dict, report: dict) -> dict:
    db_dir = config.dev_databases_dir() / db_id
    desc_dir = db_dir / "database_description"
    csvs = {f.stem.strip().lower(): f for f in desc_dir.glob("*.csv")} if desc_dir.exists() else {}
    conn = _ro(config.sqlite_path(db_id))
    tables_out, used_csv = [], set()
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in names:
        f = csvs.get(t.strip().lower())
        rows, enc = ([], None)
        if f:
            used_csv.add(f.stem.strip().lower())
            rows, enc = read_description_csv(f)
            if enc != "utf-8-sig":
                report["csv_latin1_fallback"].append(f"{db_id}/{f.name}")
        else:
            report["tables_without_csv"].append(f"{db_id}.{t}")
        by_col = {r.get("original_column_name", "").strip().lower(): r for r in rows}
        info = list(conn.execute(f'PRAGMA table_info("{t}")'))
        db_cols = {c[1].strip().lower() for c in info}
        for orphan in set(by_col) - db_cols - {""}:
            report["csv_rows_without_column"].append(f"{db_id}.{t}.{orphan}")
        fks = [{"from": r[3], "to_table": r[2], "to_column": r[4]}
               for r in conn.execute(f'PRAGMA foreign_key_list("{t}")')]
        cols = []
        for _, name, ctype, _, _, pk in info:
            r = by_col.get(name.strip().lower(), {})
            human = r.get("column_name", "")
            desc = r.get("column_description", "")
            source = "csv"
            if not desc:
                source = "auto"
                desc = human if human and human.lower() != name.lower() else humanize(name)
                report["auto_descriptions"].append(f"{db_id}.{t}.{name}")
            vdesc = r.get("value_description", "")
            cols.append({"name": name, "type": ctype or "", "is_pk": bool(pk),
                         "human_name": human or humanize(name), "description": desc,
                         "description_source": source, "value_description": vdesc,
                         "data_format": r.get("data_format", ""),
                         "samples": _samples(conn, t, name, p["sample_values"], p["sample_value_max_chars"])})
        n_rows = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        tables_out.append({"name": t, "n_rows": n_rows, "source": f"database_description/{f.name}" if f else "sqlite schema",
                           "primary_key": [c["name"] for c in cols if c["is_pk"]],
                           "foreign_keys": fks, "columns": cols})
    for stem in set(csvs) - used_csv:
        report["csv_without_table"].append(f"{db_id}/{csvs[stem].name}")
    conn.close()
    return {"db_id": db_id, "tables": tables_out}


def build_documents(schemas: dict, p: dict) -> list[dict]:
    docs, vmax = [], p["value_description_max_chars"]
    for db_id, s in schemas.items():
        for t in s["tables"]:
            col_txt = "; ".join(f"{c['name']} ({c['type']}): {c['description']}" for c in t["columns"])
            fk_txt = "; ".join(f"{f['from']} -> {f['to_table']}.{f['to_column']}" for f in t["foreign_keys"])
            docs.append({"id": f"{db_id}.{t['name']}",
                         "text": f"Table {t['name']} in database {db_id} ({t['n_rows']} rows). Columns: {col_txt}."
                                 + (f" Foreign keys: {fk_txt}." if fk_txt else ""),
                         "metadata": {"db_id": db_id, "table": t["name"], "column": "", "level": "table",
                                      "type": "", "is_pk": False, "source": t["source"]}})
            for c in t["columns"]:
                ex = f" Examples: {', '.join(c['samples'])}." if c["samples"] else ""
                vd = f" {c['value_description'][:vmax]}" if c["value_description"] else ""
                docs.append({"id": f"{db_id}.{t['name']}.{c['name']}",
                             "text": f"Column {c['name']} ({c['human_name']}) of table {t['name']} in database "
                                     f"{db_id}, type {c['type']}. {c['description']}.{vd}{ex}",
                             "metadata": {"db_id": db_id, "table": t["name"], "column": c["name"],
                                          "level": "column", "type": c["type"], "is_pk": c["is_pk"],
                                          "source": t["source"]}})
    # glossary (hand-written business definitions)
    for f in sorted(config.glossary_dir().glob("*.md")):
        if f.stem not in schemas:
            continue
        paras = [clean_text(x) for x in f.read_text(encoding="utf-8").split("\n\n")]
        for i, para in enumerate([x for x in paras if x and not x.startswith("#")]):
            docs.append({"id": f"{f.stem}.glossary.{i}", "text": f"Definition ({f.stem}): {para}",
                         "metadata": {"db_id": f.stem, "table": "", "column": "", "level": "glossary",
                                      "type": "", "is_pk": False, "source": f"glossary/{f.name}"}})
    seen = set()
    for d in docs:
        assert d["id"] not in seen, f"duplicate document id {d['id']}"
        seen.add(d["id"])
        d["metadata"]["hash"] = hashlib.sha1(d["text"].encode("utf-8")).hexdigest()
    return docs


def run() -> None:
    p = config.params()["clean"]
    report = {k: [] for k in ("csv_latin1_fallback", "tables_without_csv", "csv_rows_without_column",
                              "csv_without_table", "auto_descriptions")}
    schemas = {db: clean_database(db, p, report) for db in config.list_db_ids()}
    docs = build_documents(schemas, p)
    out = config.processed_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "schema.json").write_text(json.dumps(schemas, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    with open(out / "documents.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, sort_keys=True, ensure_ascii=False) + "\n")
    n_cols = sum(len(t["columns"]) for s in schemas.values() for t in s["tables"])
    summary = {"databases": len(schemas), "tables": sum(len(s["tables"]) for s in schemas.values()),
               "columns": n_cols, "documents": len(docs),
               **{k: len(v) for k, v in report.items()},
               "pct_columns_with_csv_description": round(100 * (1 - len(report["auto_descriptions"]) / max(n_cols, 1)), 1)}
    (out / "cleaning_report.json").write_text(
        json.dumps({"summary": summary, "details": report}, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    run()
