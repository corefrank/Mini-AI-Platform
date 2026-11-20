import asyncio

import httpx
import numpy as np
from sqlalchemy import select

from app import knowledge, llm, tasks
from app.db import Document, Session
from app.schemas import ModelView


def test_login_jwt_and_role(client, auth):
    assert client.get("/api/health").status_code == 200
    for name in ["alice", "does-not-exist"]:
        response = client.post("/api/auth/login", json={"username": name, "password": "incorrect"})
        assert response.status_code == 401
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer broken"}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth("alice")).json()["role"] == "user"
    assert client.get("/api/admin/users", headers=auth("alice")).status_code == 403
    assert len(client.get("/api/admin/users", headers=auth("admin")).json()) == 3


def test_conversation_crud_and_ownership(client, auth):
    alice, bob = auth("alice"), auth("bob")
    base = "/api/conversations"
    assert client.post(base, json={"title": "   "}, headers=alice).status_code == 422
    response = client.post(base, json={"title": "First"}, headers=alice)
    assert response.status_code == 201
    url = f"{base}/{response.json()['id']}"
    assert client.get(base, headers=bob).json() == []
    assert client.get(url, headers=bob).status_code == 404
    assert client.patch(url, headers=bob, json={"title": "Other"}).status_code == 404
    assert client.delete(url, headers=bob).status_code == 404
    assert client.patch(url, headers=alice, json={"title": "Updated"}).json()["title"] == "Updated"
    assert client.get(url, headers=alice).json()["messages"] == []
    assert client.delete(url, headers=alice).status_code == 204
    assert client.get(url, headers=alice).status_code == 404


def test_model_config_cache(client, auth, monkeypatch):
    class CacheSpy:
        values = {}
        writes = []

        def get(self, key):
            return self.values.get(key)

        def setex(self, key, ttl, value):
            self.writes.append(ttl)
            self.values[key] = value

        def delete(self, key):
            self.values.pop(key, None)

    cache = CacheSpy()
    monkeypatch.setattr(llm, "cache", cache)
    alice, admin = auth("alice"), auth("admin")
    listing = client.get("/api/models", headers=alice).json()
    assert len(listing) == 2
    url = f"/api/models/{listing[0]['id']}"
    assert client.get(url, headers=alice).json()["temperature"] == 0.2
    assert client.get(url, headers=alice).json()["temperature"] == 0.2
    assert cache.writes == [60]
    body = {"model": "openai/gpt-4o-mini", "temperature": 0.5, "max_tokens": 512}
    assert client.patch(url, headers=alice, json=body).status_code == 403
    assert client.patch(url, headers=admin, json=body).status_code == 200
    assert not cache.values
    assert client.get(url, headers=alice).json()["temperature"] == 0.5
    assert cache.writes == [60, 60]


def test_sse_success_and_failure(client, auth, monkeypatch):
    async def upstream(config, messages):
        if messages[-1]["content"] == "fail":
            yield "delta", "部分"
            raise llm.ModelError("OpenRouter HTTP 429", True)
        yield "delta", "你"
        yield "delta", "好"
        yield "usage", {"total_tokens": 11}

    monkeypatch.setattr(llm, "stream", upstream)
    alice, admin = auth("alice"), auth("admin")
    row = client.post("/api/conversations", json={"title": "Chat"}, headers=alice).json()
    url = f"/api/conversations/{row['id']}"
    model_id = client.get("/api/models", headers=alice).json()[0]["id"]
    response = client.post(url + "/stream", json={"model_id": model_id, "message": "test"}, headers=alice)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count("event: delta\n") == 2
    assert 'event: done\ndata: {"citations": [], "usage": {"total_tokens": 11}}\n\n' in response.text
    assert client.get(url, headers=alice).json()["messages"][1]["content"] == "你好"
    bad = client.post(url + "/stream", json={"model_id": model_id, "message": "fail"}, headers=alice)
    assert "event: error\n" in bad.text and "event: done\n" not in bad.text
    assert len(client.get(url, headers=alice).json()["messages"]) == 2
    rows = client.get("/api/admin/logs", params={"request_id": bad.headers["X-Request-ID"]}, headers=admin).json()
    assert rows[0]["status"] == "FAILED" and rows[0]["error"] == "OpenRouter HTTP 429"


def test_upstream_transport_stream_checks_and_retry(monkeypatch):
    attempts = []

    async def provider(request):
        attempts.append(request.url.path)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=(
            ': keepalive\n\ndata: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            'data: {"choices":[],"usage":{"total_tokens":4,"other":"excluded"}}\n\ndata: [DONE]\n\n'
        ))

    monkeypatch.setattr(llm, "client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(provider)))
    config = ModelView(id=1, label="test", model="openai/gpt-4o-mini", temperature=0.2, max_tokens=128)

    async def read():
        return [event async for event in llm.stream(config, [])]

    assert asyncio.run(read()) == [("delta", "hello"), ("usage", {"total_tokens": 4})]
    assert len(attempts) == 2


def test_index_job_and_isolation(client, auth, monkeypatch):
    sent = []
    monkeypatch.setattr(tasks.execute_job, "apply_async", lambda **kwargs: sent.append(kwargs["task_id"]))
    # 用确定性小矩阵替代模型下载，FAISS 建盘及检索仍使用真实实现。
    monkeypatch.setattr(knowledge, "embed", lambda texts: np.array(
        [[1.0, 0.0] if "ttl" in value.lower() else [0.0, 1.0] for value in texts], dtype="float32"))
    alice, bob = auth("alice"), auth("bob")
    response = client.post("/api/documents", headers=alice, data={"source_id": "redis-expire"},
                           files={"file": ("redis.md", b"Redis TTL sets a key expiration.")})
    assert response.status_code == 202
    doc_id, task_id = response.json()["document_id"], response.json()["task_id"]
    url = f"/api/tasks/{task_id}"
    assert sent == [task_id]
    assert client.get(url, headers=alice).json()["status"] == "PENDING"
    assert client.get(url, headers=bob).status_code == 404
    assert client.get(f"/api/documents/{doc_id}", headers=bob).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 409
    tasks.execute_job.run(task_id)
    assert client.get(url, headers=alice).json()["status"] == "SUCCESS"
    with Session() as db:
        doc = db.get(Document, doc_id)
        assert knowledge.index_path(doc.user_id, doc.id).is_file()
    for method in ["vector", "bm25"]:
        query = f"/api/search?q=Redis+TTL&method={method}"
        assert client.get(query, headers=alice).json()[0]["source_id"] == "redis-expire"
        assert client.get(query, headers=bob).json() == []
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 204
    assert client.get("/api/search?q=Redis+TTL", headers=alice).json() == []


def test_agent_tool_and_log(client, auth, monkeypatch):
    monkeypatch.setattr(tasks.execute_job, "apply_async", lambda **kwargs: None)
    bodies = []

    async def completion(config, messages, tools):
        bodies.append((list(messages), tools))
        if len(bodies) == 1:
            return {"content": None, "tool_calls": [{
                "id": "read-1", "type": "function",
                "function": {"name": "read_document", "arguments": '{"document_id":1}'}}]}, None
        return {"content": "见 [D1]"}, {"total_tokens": 15}

    monkeypatch.setattr(tasks, "complete", completion)
    alice, admin = auth("alice"), auth("admin")
    with Session.begin() as db:
        from app.db import User
        owner = db.scalar(select(User.id).where(User.username == "alice"))
        doc = Document(id=1, user_id=owner, title="Guide", filename="guide.md", content="Evidence", status="READY")
        db.add(doc)
    model_id = client.get("/api/models", headers=alice).json()[0]["id"]
    start = client.post("/api/agent/tasks", headers=alice, json={"model_id": model_id, "prompt": "Read the guide"})
    assert start.status_code == 202
    job = start.json()
    tasks.execute_job.run(job["id"])
    result = client.get(f"/api/tasks/{job['id']}", headers=alice).json()
    assert result["result"]["trace"][0]["status"] == "SUCCESS"
    assert result["result"]["citations"][0]["excerpt"] == "Evidence"
    assert bodies[1][0][-1]["role"] == "tool"
    logs = client.get("/api/admin/logs", headers=admin).json()
    assert any(row["usage"] == {"total_tokens": 15} for row in logs)


def test_broker_failure_marks_document_and_task(client, auth, monkeypatch):
    def offline(**kwargs):
        raise ConnectionError("test broker is offline")

    monkeypatch.setattr(tasks.execute_job, "apply_async", offline)
    headers = auth("alice")
    uploaded = client.post("/api/documents", headers=headers, files={"file": ("topic.txt", b"Celery")}).json()
    assert uploaded["status"] == "FAILED"
    task = client.get(f"/api/tasks/{uploaded['task_id']}", headers=headers).json()
    assert task["status"] == "FAILED" and "Broker" in task["error"]
    assert client.get("/api/documents", headers=headers).json()[0]["status"] == "FAILED"
