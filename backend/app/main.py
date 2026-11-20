import logging
import os
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import chat, knowledge, llm, tasks
from .common import Admin, Identity, dummy_hash, issue_token, logger, owned, passwords
from .db import CallLog, Document, Job, ModelConfig, Session, User
from .schemas import AgentInput, Id, Login, ModelEdit, ModelView

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
app = FastAPI(title="Mini AI Platform", version="0.1.0", docs_url="/api/docs",
              redoc_url=None, openapi_url="/api/openapi.json")
api = "/api"
app.include_router(chat.router, prefix=api)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"], expose_headers=["X-Request-ID"])


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error_response(request, status, message, headers=None):
    request_id = request.state.request_id
    return JSONResponse(status_code=status, content={"error": {"message": message,
                        "request_id": request_id}}, headers={**(headers or {}), "X-Request-ID": request_id})


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    return error_response(request, exc.status_code, exc.detail, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    fields = ", ".join(".".join(map(str, err["loc"])) for err in exc.errors())
    return error_response(request, 422, f"请求参数不符合要求（{fields}）")


@app.exception_handler(Exception)
async def server_error(request, exc):
    logger.error("request_failed request_id=%s type=%s", request.state.request_id, type(exc).__name__)
    return error_response(request, 500, "服务内部错误")


@app.get(api + "/health")
def health():
    with Session() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


def user_view(user):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post(api + "/auth/login")
def login(body: Login):
    with Session() as db:
        user = db.scalar(select(User).where(User.username == body.username))
    valid = passwords.verify(body.password, user.password_hash if user else dummy_hash)
    if user is None or not valid:
        raise HTTPException(401, "用户名或密码不正确")
    return {"access_token": issue_token(user.id), "token_type": "bearer", "user": user_view(user)}


@app.get(api + "/auth/me")
def me(user: Identity):
    return user_view(user)


@app.get(api + "/models", response_model=list[ModelView])
def models(user: Identity):
    with Session() as db:
        return db.scalars(select(ModelConfig).order_by(ModelConfig.id)).all()


@app.get(api + "/models/{model_id}", response_model=ModelView)
def model_detail(model_id: Id, user: Identity):
    config = llm.get_model(model_id)
    if not config:
        raise HTTPException(404, "模型配置不存在")
    return config


@app.patch(api + "/models/{model_id}", response_model=ModelView)
def edit_model(model_id: Id, body: ModelEdit, admin: Admin):
    with Session.begin() as db:
        row = db.get(ModelConfig, model_id)
        if not row:
            raise HTTPException(404, "模型配置不存在")
        row.model, row.temperature, row.max_tokens = body.model, body.temperature, body.max_tokens
    llm.invalidate_model(model_id)
    return row


@app.get(api + "/admin/users")
def users(admin: Admin):
    with Session() as db:
        return [user_view(row) for row in db.scalars(select(User).order_by(User.id))]


@app.get(api + "/admin/logs")
def logs(admin: Admin, limit: Annotated[int, Query(ge=1, le=200)] = 100,
         request_id: Annotated[str | None, Query(pattern=r"^[a-f0-9]{32}$")] = None):
    statement = select(CallLog).order_by(CallLog.id.desc()).limit(limit)
    if request_id:
        statement = statement.where(CallLog.request_id == request_id)
    with Session() as db:
        return [{column.name: getattr(row, column.name) for column in CallLog.__table__.columns}
                for row in db.scalars(statement)]


class DocView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    filename: str
    source_url: str
    source_id: str
    source_version: str
    category: str
    license: str
    status: str


@app.get(api + "/documents", response_model=list[DocView])
def documents(user: Identity):
    with Session() as db:
        return db.scalars(select(Document).where(Document.user_id == user.id)
                          .order_by(Document.id.desc())).all()


@app.post(api + "/documents", status_code=202)
def upload_document(
    user: Identity, request: Request, file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(max_length=160)] = "",
    source_url: Annotated[str, Form(max_length=450, pattern=r"^(https?://.+)?$")] = "",
    source_id: Annotated[str, Form(max_length=100)] = "",
    category: Annotated[str, Form(max_length=80)] = "",
    source_version: Annotated[str, Form(max_length=120)] = "",
    license: Annotated[str, Form(max_length=120)] = "",
):
    filename = PurePosixPath((file.filename or "").replace("\\", "/")).name
    if not filename or len(filename) > 180 or PurePosixPath(filename).suffix.lower() not in {".md", ".txt"}:
        raise HTTPException(422, "请选择 TXT 或 Markdown 文档")
    limit = 512 * 1024
    raw = file.file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(413, "单篇文档最多 512 KiB")
    try:
        content = raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise HTTPException(422, "文档需要 UTF-8 编码") from None
    if not content or "\x00" in content:
        raise HTTPException(422, "文档没有有效文本")
    with Session() as db:
        doc = Document(user_id=user.id, filename=filename, title=title.strip() or filename[:160],
                       source_url=source_url, source_id=source_id, category=category,
                       source_version=source_version, license=license, content=content)
        db.add(doc)
        db.flush()
        job = tasks.submit_job(db, user.id, "index", {"document_id": doc.id}, request.state.request_id)
        return {"document_id": doc.id, "task_id": job.id, "status": job.status}


@app.get(api + "/documents/{document_id}")
def read_document(document_id: Id, user: Identity):
    with Session() as db:
        doc = owned(db, Document, document_id, user.id)
        return {**DocView.model_validate(doc).model_dump(), "content": doc.content}


@app.delete(api + "/documents/{document_id}", status_code=204)
def delete_document(document_id: Id, user: Identity):
    with Session.begin() as db:
        doc = owned(db, Document, document_id, user.id)
        if doc.status in {"PENDING", "RUNNING"}:
            raise HTTPException(409, "文档任务进行中")
        db.delete(doc)
    try:
        knowledge.index_path(user.id, document_id).unlink(missing_ok=True)
    except OSError:
        logger.warning("index_cleanup_failed document_id=%s", document_id)


@app.get(api + "/search")
def search(
    user: Identity, q: Annotated[str, Query(min_length=2, max_length=500)],
    method: Literal["vector", "bm25"] = "vector", k: Annotated[int, Query(ge=1, le=10)] = 5,
):
    with Session() as db:
        return knowledge.retrieve(db, user.id, q, k, method)


def task_view(job):
    return {"id": job.id, "task_type": job.task_type, "status": job.status, "result": job.result,
            "error": job.error, "request_id": job.request_id, "attempts": job.attempts,
            "created_at": job.created_at}


@app.post(api + "/agent/tasks", status_code=202)
def agent_task(body: AgentInput, user: Identity, request: Request):
    if not llm.get_model(body.model_id):
        raise HTTPException(404, "模型配置不存在")
    with Session() as db:
        return task_view(tasks.submit_job(db, user.id, "agent", body.model_dump(),
                                          request.state.request_id))


@app.get(api + "/tasks")
def task_list(user: Identity):
    with Session() as db:
        rows = db.scalars(select(Job).where(Job.user_id == user.id)
                          .order_by(Job.created_at.desc()).limit(100))
        return [task_view(row) for row in rows]


@app.get(api + "/tasks/{task_id}")
def task_detail(task_id: UUID, user: Identity):
    with Session() as db:
        return task_view(owned(db, Job, str(task_id), user.id))
