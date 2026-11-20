"""用真实 HTTP 接口导入文档、评测检索或验证 OpenRouter 工作流。"""
import argparse
import getpass
import json
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def data(response):
    response.raise_for_status()
    return response.json() if response.status_code != 204 else None


def login(http, user, password):
    token = data(http.post("/api/auth/login", json={"username": user, "password": password}))
    http.headers["Authorization"] = f'Bearer {token["access_token"]}'


def import_documents(http, args):
    directory = args.directory
    entries = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    already = {row["source_id"]: row for row in data(http.get("/api/documents")) if row["source_id"]}
    for entry in entries:
        source_id = entry["document_id"]
        existing = already.get(source_id)
        if existing:
            if existing["status"] != "FAILED" or not args.retry_failed:
                continue
            data(http.delete(f'/api/documents/{existing["id"]}'))
        fields = {name: entry[name] for name in ("title", "source_url", "category", "license")}
        fields.update(source_id=source_id, source_version=entry["revision"] + " @ " + entry["retrieved_on"])
        filename = entry["filename"]
        with (directory / filename).open("rb") as f:
            data(http.post("/api/documents", data=fields, files={"file": (filename, f, "text/plain")}))
    deadline = time.monotonic() + args.wait
    wanted = {entry["document_id"] for entry in entries}
    while True:
        rows = [row for row in data(http.get("/api/documents")) if row["source_id"] in wanted]
        ready = sum(row["status"] == "READY" for row in rows)
        failed = [row["source_id"] for row in rows if row["status"] == "FAILED"]
        if ready + len(failed) >= len(wanted) or time.monotonic() > deadline:
            print(f"READY {ready}/{len(wanted)}; FAILED {len(failed)}; pending {len(wanted) - ready - len(failed)}")
            if failed:
                print("Failed:", ", ".join(failed))
            if ready != len(wanted):
                raise SystemExit(1)
            return
        time.sleep(2)


def evaluate(http, args):
    questions = json.loads((ROOT / "data/evaluation/questions.json").read_text(encoding="utf-8"))
    indexed = {row["source_id"] for row in data(http.get("/api/documents")) if row["status"] == "READY"}
    expected = {entry["document_id"] for row in questions for entry in row["references"]}
    if expected - indexed:
        raise SystemExit("请先导入完整知识库。缺少：" + ", ".join(sorted(expected - indexed)))
    results = {}
    for method in ("vector", "bm25"):
        details = []
        for question in questions:
            key = "query_zh" if args.language == "zh" else "query"
            hits = data(http.get("/api/search", params={"q": question[key], "method": method, "k": 5}))
            source_ids = {hit["source_id"] for hit in hits}
            required = {entry["document_id"] for entry in question["references"]}
            details.append({"id": question["id"], "type": question["type"],
                            "retrieved": [hit["source_id"] for hit in hits],
                            "recall": len(source_ids & required) / len(required) if required else None})
        recalls = [row["recall"] for row in details if row["recall"] is not None]
        results[method] = {"recall_at_5": sum(recalls) / len(recalls),
                           "hit_at_5": sum(value > 0 for value in recalls) / len(recalls),
                           "answerable": len(recalls), "details": details}
        print(f"{method}: Recall@5 {results[method]['recall_at_5']:.2%}; "
              f"Hit@5 {results[method]['hit_at_5']:.2%}; n={len(recalls)}")
    args.output.write_text(json.dumps({"language": args.language, "results": results}, indent=2) + "\n",
                           encoding="utf-8")


def read_stream(http, path, payload):
    events = []
    with http.stream("POST", path, json=payload, timeout=150) as response:
        response.raise_for_status()
        kind = None
        for line in response.iter_lines():
            if line.startswith("event:"):
                kind = line[6:].strip()
            elif line.startswith("data:") and kind:
                body = json.loads(line[5:])
                if kind == "error":
                    raise RuntimeError(body["message"])
                events.append((kind, body))
                kind = None
    if not events or events[-1][0] != "done" or not any(key == "delta" for key, _ in events):
        raise RuntimeError("SSE 未正常生成并结束")
    return events


def smoke(http):
    models = data(http.get("/api/models"))
    if len(models) < 2:
        raise SystemExit("需要两种模型配置")
    docs = data(http.get("/api/documents"))
    if not any(doc["status"] == "READY" for doc in docs):
        raise SystemExit("请先导入至少一篇 READY 文档")
    conversation = data(http.post("/api/conversations", json={"title": "OpenRouter 实测"}))["id"]
    base = f"/api/conversations/{conversation}"
    for model in models[:2]:
        events = read_stream(http, base + "/stream", {"model_id": model["id"], "message": "Say hello in one sentence"})
        print(f'{model["model"]}: SSE done, {sum(key == "delta" for key, _ in events)} delta events')
    model_id = models[0]["id"]
    events = read_stream(http, base + "/stream", {
        "model_id": model_id, "mode": "rag", "message": "How can a Redis EXPIRE timeout be inspected?",
    })
    if not events[-1][1]["citations"]:
        raise RuntimeError("RAG 未返回证据")
    if len(data(http.get(base))["messages"]) != 6:
        raise RuntimeError("会话历史记录条数不符")
    print("RAG: citations and 6 persisted messages")
    job = data(http.post("/api/agent/tasks", json={
        "model_id": model_id, "prompt": "Compare FastAPI BackgroundTasks and Celery. Cite evidence.",
    }))
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        job = data(http.get(f'/api/tasks/{job["id"]}'))
        if job["status"] == "FAILED":
            raise RuntimeError(job["error"])
        if job["status"] == "SUCCESS":
            result = job["result"]
            if not all(result.get(key) for key in ("report", "trace", "citations")):
                raise RuntimeError("Agent 未返回报告、轨迹或证据")
            print("Agent: report, trace and citations")
            return
        time.sleep(2)
    raise TimeoutError("Agent 超时，详情请见任务中心")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="alice")
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import")
    importer.add_argument("--directory", type=Path, default=ROOT / "data/documents")
    importer.add_argument("--retry-failed", action="store_true")
    importer.add_argument("--wait", type=int, default=600)
    evaluator = commands.add_parser("evaluate")
    evaluator.add_argument("--language", choices=["en", "zh"], default="en")
    evaluator.add_argument("--output", type=Path, default=ROOT / "data/last-eval.json")
    commands.add_parser("smoke-openrouter")
    args = parser.parse_args()
    password = os.getenv("MINI_AI_PASSWORD") or getpass.getpass(f"Password for {args.user}: ")
    with httpx.Client(base_url=args.url, timeout=60, trust_env=False) as http:
        login(http, args.user, password)
        if args.command == "import":
            import_documents(http, args)
        elif args.command == "evaluate":
            evaluate(http, args)
        else:
            smoke(http)


if __name__ == "__main__":
    main()
