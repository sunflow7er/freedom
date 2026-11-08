import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
import httpx


FAKE_RECORD = {
    "conversation_id": "test-ru-001",
    "channel": "agent chat",
    "language": "RU",
    "transcript": [
        {"timestamp": "00:01", "speaker": "operator", "text": "Здравствуйте!"},
        {"timestamp": "00:10", "speaker": "client", "text": "Привет"},
    ],
    "audio_url": None,
}

FAKE_API_RESPONSE = {
    "error": "",
    "isSuccess": True,
    "data": {
        "dataset_group_id": "DEV",
        "total_records": 1,
        "records": [FAKE_RECORD],
    },
}


@pytest.fixture()
def client_with_db(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("backend.app.db.DB_PATH", db_path):
        from backend.app.db import create_tables
        create_tables()
        with patch.dict("os.environ", {"DATASET_API_URL": "http://fake/api?group_id=DEV"}):
            from fastapi.testclient import TestClient
            from backend.app.main import app
            with TestClient(app) as c:
                yield c


def test_import_and_list(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("backend.app.db.DB_PATH", db_path):
        from backend.app.db import create_tables
        create_tables()
        with patch.dict("os.environ", {"DATASET_API_URL": "http://fake/api?group_id=DEV"}):
            from fastapi.testclient import TestClient
            from backend.app.main import app

            mock_resp = httpx.Response(200, json=FAKE_API_RESPONSE)
            with patch("backend.app.dataset.httpx.AsyncClient") as mock_cls:
                mock_instance = AsyncMock()
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_instance.get = AsyncMock(return_value=mock_resp)

                with TestClient(app) as client:
                    resp = client.post("/api/datasets/DEV/import")

            assert resp.status_code == 200
            data = resp.json()
            assert data["inserted"] == 1
            assert data["skipped"] == 0

            with TestClient(app) as client:
                resp2 = client.get("/api/conversations")
                assert resp2.status_code == 200
                convs = resp2.json()
                assert len(convs) == 1
                assert convs[0]["id"] == "test-ru-001"

                resp3 = client.get("/api/conversations/test-ru-001")
                assert resp3.status_code == 200
                conv = resp3.json()
                assert isinstance(conv["transcript"], list)
                assert conv["transcript"][0]["text"] == "Здравствуйте!"


def test_import_skips_duplicates(tmp_path):
    db_path = tmp_path / "test.db"
    with patch("backend.app.db.DB_PATH", db_path):
        from backend.app.db import create_tables
        create_tables()
        with patch.dict("os.environ", {"DATASET_API_URL": "http://fake/api?group_id=DEV"}):
            from fastapi.testclient import TestClient
            from backend.app.main import app

            mock_resp = httpx.Response(200, json=FAKE_API_RESPONSE)
            with patch("backend.app.dataset.httpx.AsyncClient") as mock_cls:
                mock_instance = AsyncMock()
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_instance.get = AsyncMock(return_value=mock_resp)

                with TestClient(app) as client:
                    client.post("/api/datasets/DEV/import")
                    resp = client.post("/api/datasets/DEV/import")

            assert resp.json()["inserted"] == 0
            assert resp.json()["skipped"] == 1
