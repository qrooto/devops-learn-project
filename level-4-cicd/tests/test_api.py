"""
Базовые тесты API. Запускаются в CI перед сборкой образа.
Используют TestClient который поднимает FastAPI без реального сервера.
БД и Redis замокированы — тесты быстрые и не требуют инфраструктуры.
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Мокируем зависимости до импорта main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../level-3-caching/backend'))

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"
os.environ["REDIS_URL"] = "redis://localhost:6379"


@pytest.fixture(autouse=True)
def mock_infrastructure():
    """Мокируем PostgreSQL и Redis чтобы тесты не требовали инфраструктуры."""
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = True
    mock_redis.delete.return_value = 1

    with patch('sqlalchemy.create_engine', return_value=mock_engine), \
         patch('redis.from_url', return_value=mock_redis):
        import importlib
        import main as app_module
        importlib.reload(app_module)
        yield app_module, mock_conn, mock_redis


def test_health(mock_infrastructure):
    app_module, _, _ = mock_infrastructure
    client = TestClient(app_module.app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_ads_empty(mock_infrastructure):
    app_module, mock_conn, _ = mock_infrastructure
    mock_conn.execute.return_value.fetchall.return_value = []
    client = TestClient(app_module.app)
    res = client.get("/api/ads")
    assert res.status_code == 200
    assert res.json() == []


def test_create_ad(mock_infrastructure):
    app_module, mock_conn, _ = mock_infrastructure
    mock_conn.execute.return_value.fetchone.return_value = (42,)
    client = TestClient(app_module.app)
    res = client.post("/api/ads", json={
        "title": "Тест",
        "description": "Описание",
        "price": 1000,
        "author": "Тестер"
    })
    assert res.status_code == 201
    assert res.json()["id"] == 42
