"""Check SQL for safety, then run it on a read-only connection."""

import sqlite3
import time

import sqlglot
from sqlglot import exp

from src.config import ROW_LIMIT, TIMEOUT_SECONDS, database_path

FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
             exp.Command, exp.Pragma, exp.Attach, exp.Detach, exp.Into)
FORBIDDEN_FUNCTIONS = ("load_extension", "readfile", "writefile")  # file / native code access


def validate_sql(sql):
    """Return (True, "") for a single SELECT query, (False, reason) otherwise."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except sqlglot.errors.ParseError as error:
        return False, f"Invalid SQL: {error}"
    if len(statements) != 1:
        return False, "Exactly one SQL statement is allowed."
    query = statements[0]
    if not isinstance(query, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return False, "Only SELECT queries are allowed."
    for node in query.walk():
        if isinstance(node, FORBIDDEN):
            return False, f"Forbidden operation: {node.key.upper()}"
        if isinstance(node, exp.Anonymous) and node.name.lower() in FORBIDDEN_FUNCTIONS:
            return False, f"Forbidden function: {node.name}"
    return True, ""


def run_sql(db_id, sql, timeout=TIMEOUT_SECONDS):
    """Validate, then run the query read-only. Errors are returned, not raised."""
    ok, reason = validate_sql(sql)
    if not ok:
        return {"ok": False, "error": reason}

    # mode=ro: the database file is opened read-only, a second layer of protection
    conn = sqlite3.connect(f"file:{database_path(db_id).as_posix()}?mode=ro", uri=True)
    deadline = time.time() + timeout
    conn.set_progress_handler(lambda: time.time() > deadline, 10_000)  # stops slow queries
    try:
        cursor = conn.execute(sql)
        columns = [c[0] for c in cursor.description]
        rows = [[v if not isinstance(v, bytes) else "<binary>" for v in r]
                for r in cursor.fetchmany(ROW_LIMIT)]
        return {"ok": True, "sql": sql, "columns": columns, "rows": rows}
    except sqlite3.Error as error:
        message = "Query took too long." if "interrupted" in str(error) else str(error)
        return {"ok": False, "error": message}
    finally:
        conn.close()
