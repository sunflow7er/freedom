import sqlite3
import tempfile
import os
import pytest
from pathlib import Path
from unittest.mock import patch


def make_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    with patch("backend.app.db.DB_PATH", db_path):
        from backend.app.db import create_tables, get_db
        create_tables()
        return get_db(), db_path


def test_tables_created(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("backend.app.db.DB_PATH", db_path):
        from backend.app.db import create_tables, get_db
        create_tables()
        conn = get_db()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    expected = {
        "conversations", "checklists", "checklist_versions",
        "evaluations", "criterion_results", "appeals", "decisions",
    }
    assert expected.issubset(tables)


def test_health_endpoint(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("backend.app.db.DB_PATH", db_path):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        client = TestClient(app)
        resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "time" in data
