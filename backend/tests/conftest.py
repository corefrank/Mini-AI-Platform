import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app import db
from app.main import app
from app.seed import seed

DEMO = "test-fixture-password"


@pytest.fixture(scope="session")
def engine(tmp_path_factory):
    # 默认 SQLite 仅用于快速测试。可显式指向专用 PostgreSQL 测试库。
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path_factory.mktemp('db') / 'test.db'}"
    engine = create_engine(url, hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine, tmp_path, monkeypatch):
    from app import knowledge, seed as seeding
    monkeypatch.setattr(seeding, "engine", engine)
    monkeypatch.setattr(knowledge, "STORE", tmp_path)
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-fixtures-only-000000000000")
    monkeypatch.setenv("DEMO_PASSWORD", DEMO)
    db.Session.configure(bind=engine)
    assert not set(db.Base.metadata.tables).intersection(inspect(engine).get_table_names()), (
        "TEST_DATABASE_URL 必须指向空的专用测试库"
    )
    seed()
    with TestClient(app) as client:
        yield client
    db.Base.metadata.drop_all(engine)
    db.Session.configure(bind=db.engine)


@pytest.fixture
def auth(client):
    def login(name):
        result = client.post("/api/auth/login", json={"username": name, "password": DEMO})
        assert result.status_code == 200, result.text
        return {"Authorization": "Bearer " + result.json()["access_token"]}
    return login
