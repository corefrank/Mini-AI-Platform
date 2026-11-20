# 七阶段开发记录

各阶段的命令列出开发中实际执行的关键检查。用 Docker Compose 启动 Windows 版全栈的命令见 README。验收环境与 Mock 边界见 [验收记录](docs/VERIFICATION.md)。

## Day 1 · FastAPI 和 PostgreSQL

- **完成与文件**：`db.py` 定义七张表与 Session。`schemas.py` 定义 Pydantic 入参。`chat.py` 定义会话 CRUD。`main.py` 挂路由、Swagger、健康检查与错误响应。
- **调用链**：HTTP JSON → Pydantic → SQLAlchemy Session → PostgreSQL → JSON/状态码。
- **执行与结果**：`uv --system-certs lock` 和 `uv sync --locked` 成功。用 PostgreSQL 17 的 `initdb`、`postgres` 启动临时测试库。API 的 `GET /api/health` 为 200，真实 PostgreSQL 上的 CRUD 测试通过。
- **待验与岗位**：在 Windows 用 Swagger 复现 CRUD。覆盖 REST、数据校验、数据库和 ORM。

## Day 2 · Vue 与联调

- **完成与文件**：`package.json` 和 `vite.config.js` 管前端依赖和代理。`src/main.js` 注册路由。`src/api.js` 封装请求与会话状态。`Chat.vue` 对接会话创建、改名和删除。随后接入其余四个页面。
- **调用链**：Vue 组件响应事件 → Fetch → Vite `/api` proxy → FastAPI → 更新响应式状态。
- **执行与结果**：`npm install --no-audit --no-fund`、`npm run build` 成功。真实 HTTP 测试通过 Vite 代理登录、读文档和任务、验证权限。单个前端 bundle 大于 Vite 建议值，MVP 保留当前组件注册方式。
- **待验与岗位**：浏览器运行环境缺少 Unix Socket 支持，Chromium 未能启动。覆盖前后端分离、Vue、联调与表单表格。

## Day 3 · JWT 与资源归属

- **完成与文件**：`seed.py` 初始化三个账户；`common.py` 统一 Argon2、JWT、Admin/User 与用户归属判断；`Login.vue` 承接登录；`main.js` 做页面路由守卫。
- **调用链**：登录验密码 → 签发 JWT → 请求校验签名与时效 → 查询角色与资源所有者。
- **执行与结果**：`python -m app.seed` 成功。`pytest -q` 中登录成功／失败、401、403、跨用户 404 通过。真实 HTTP 测试验证 Bob 无法查到 Alice 的文档与会话。
- **待验与岗位**：Windows 浏览器验证实际账号切换。覆盖认证、权限、后台用户管理。

## Day 4 · 统一模型与 SSE

- **完成与文件**：`llm.py` 管并发 I/O、上游普通调用、流式读取和有限重试。`chat.py` 管 SSE 和历史提交。`frontend/src/sse.js` 解析事件并交给 `Chat.vue` 渲染。
- **调用链**：Vue POST + JWT → FastAPI → HTTPX 增量读取 → SSE 转发 → 事务保存历史 → done。
- **执行与结果**：`npm --prefix frontend test` 为 2/2。`pytest -q` 的 SSE 测试通过。真实服务器验证缺 Key 错误。本机模拟上游加真实代理测试，两套模型配置分别传出 2 条增量，断开日志正确。
- **待验与岗位**：待配置真实 Key 完成模型与浏览器流式验收。覆盖模型统一接入、超时和 SSE。

## Day 5 · Redis 和 Celery

- **完成与文件**：`tasks.py` 定义 Celery、发布、执行、重试和 PG 任务状态。`llm.py` 负责 cache-aside。`Tasks.vue` 定时查询并展示进度与结果。
- **调用链**：API 保存 job → Redis Broker → Worker → PostgreSQL 更新状态 → Vue 轮询。缓存使用 Redis 的另一逻辑数据库。
- **执行与结果**：实际执行 `redis-server` 与 `celery -A app.tasks:celery worker --concurrency=1 -l INFO`。真实 Redis 的 Miss、Hit、TTL、删除键和回填已验证。模拟上游 503 后真实 Worker 第二次尝试成功。
- **待验与岗位**：Windows Compose 容器的服务通信仍需复验。覆盖异步任务、消息队列、缓存与异常重试。

## Day 6 · 知识库与分析 Agent

- **完成与文件**：`knowledge.py` 实现分块、CPU Embedding、FAISS、BM25。`tasks.py` 接入两个受控只读工具。`data/sources.json` 固定 80 篇来源。`questions.json` 定义 30 道题。`fetch_docs.py` 下载，`platform_cli.py` 导入与评测。
- **调用链**：上传 → 后台构建索引 → Top-K 证据 → RAG SSE，或工具调用 → Markdown 报告。
- **执行与结果**：`python scripts/fetch_docs.py` 下载 80/80。`platform_cli.py import` 通过真实 API 到 Worker，READY 80/80。`evaluate` 和 `evaluate --language zh` 实测结果已保留。真实向量检索与跨用户隔离通过。
- **待验与岗位**：真实 OpenRouter 工具调用、生成质量及无证据题需本地评估。覆盖 RAG、Agent、异步索引和前端展示。

## Day 7 · 日志、测试与交付

- **完成与文件**：`common.record_call` 及 `main.logs` 关联日志，`backend/tests/` 提供自动化回归，Dockerfile 和 Compose 定义五个服务及卷。附 README、架构、学习、面试、评测与验收文档。
- **调用链**：请求 ID → API/任务日志 → Admin 查询。Nginx 和 API、Worker、数据库通过 Compose 默认网络连接。
- **执行与结果**：SQLite 和真实 PostgreSQL 上 pytest 各 8/8，Node 测试 2/2，Vite 构建通过。`docker compose config --services` 列出五个服务。Docker 守护进程在启动 containerd 时被 Unix Socket 限制阻断。
- **待验与岗位**：按 README 补齐 Windows Docker Desktop、浏览器和真实 OpenRouter 三项验收。覆盖日志定位、测试维护和容器化交付。
