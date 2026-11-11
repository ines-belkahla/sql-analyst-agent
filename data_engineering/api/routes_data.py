"""Person A-owned read-only data endpoints.

Mount this router from Person B's FastAPI application:
    from data_engineering.api.routes_data import router as data_router
    app.include_router(data_router, prefix="/api")

These endpoints expose only the cleaned schema and cleaning report.
They do not execute SQL and do not expose raw database files.
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from data_engineering import config, schema_store

router = APIRouter(tags=["data"])

@router.get("/databases")
def databases():
    """Return available databases and their schema sizes."""
    try:
        return schema_store.list_databases()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@router.get("/databases/{db_id}/schema")
def database_schema(db_id: str):
    """Return the cleaned schema for one database."""
    try:
        return schema_store.get_schema(db_id)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=f"Unknown or unavailable database: {db_id}") from exc

@router.get("/quality-report")
def quality_report():
    """Return the latest data-cleaning report."""
    report_path: Path = config.processed_dir() / "cleaning_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=503, detail="Cleaning report not found. Run the DVC pipeline first.")
    return json.loads(report_path.read_text(encoding="utf-8"))
