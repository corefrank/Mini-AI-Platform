# 七阶段学习指南

每个阶段用「先操作 → 画调用链 → 改一处 → 重新验证」的顺序。已经有 Agent 和 RAG 基础时，可把最多时间花在 Day 2、Day 4 和 Day 5。路径均相对于项目根目录。

## Day 1 · FastAPI、REST 和 PostgreSQL

- **必须掌握**：路径／查询参数、JSON Body、状态码、Pydantic 校验、SQLAlchemy Session、事务、主键和外键。
- **必读文件与函数**：`backend/app/db.py` 的 `Conversation` / `Message`。`chat.py` 的 `create_conversation`、`get_conversation`、`rename_conversation`。按 POST → ORM 对象 → flush → 提交 → JSON 顺序追踪。
- **可跳过**：`db.py` 的 Job/Log 字段和索引文件操作。
- **独立练习**：把会话标题上限改到 60，使用 Swagger 分别发送 60 字、61 字和空标题，解释客户端收到的状态码。先运行登录接口以获得 JWT。
- **参考**：[FastAPI 请求体](https://fastapi.tiangolo.com/tutorial/body/)、[SQLAlchemy ORM quickstart](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)。

## Day 2 · Vue 与联调

- **必须掌握**：`ref` 的 `.value`、模板自动解包、`v-model`、事件绑定、`onMounted`、表格数据、Fetch、路由与同源。
- **必读文件与函数**：`frontend/src/main.js` 的路由表，`api.js` 的 `request`，`pages/Chat.vue` 的 `load`、`createConversation` 和 `renameConversation`。
- **可跳过**：Element Plus 样式、Nginx、SSE 字节解析。
- **独立练习**：给会话列表添加前端标题过滤，用 Developer Tools 对照 Vue 数据与请求 JSON。切到 `npm run dev` 对照 Vite proxy。
- **参考**：[Vue 中文教程](https://cn.vuejs.org/tutorial/)、[Element Plus 表格](https://element-plus.org/zh-CN/component/table.html)、[FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/)。

## Day 3 · JWT、角色与资源归属

- **必须掌握**：密码哈希与 JWT 签名、Authorization Header、401/403/404、角色检查和行记录归属。
- **必读文件与函数**：`backend/app/seed.py` 的 `seed`，`main.py` 的 `login`，`common.py` 的 `issue_token`、`current_user`、`admin_user`、`owned`，以及 `frontend/src/main.js` 的路由守卫。
- **可跳过**：时间字段的序列化、Element Plus 登录表单样式。
- **独立练习**：Alice 创建会话后，用 Bob 登录并手工 GET 会话 ID。成功复现 404 后，解释为什么把管理员菜单隐藏仍需要后端检查。
- **参考**：[FastAPI 密码哈希与 JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)、[PyJWT](https://pyjwt.readthedocs.io/)。

## Day 4 · 模型统一接入、异步 I/O 和 SSE

- **必须掌握**：协程等待 I/O 时如何让出执行权，异步生成器如何逐段 yield，SSE 相对于普通 JSON 的差异，以及保存历史的时机。
- **必读文件与函数**：`llm.py` 的 `request_body`、`stream_once`、`stream`；`chat.py` 的 `chat_stream`、`save_turn`；`frontend/src/api.js` 的 `chatEvents`、`sse.js` 的 `consumeEvents`。
- **可跳过**：上游错误代码全集、Redis 配置类、Agent 工具。
- **独立练习**：在发送 `delta` 的分支增加一个测试计数并打印到浏览器 console。用 Network 看帧。模型调用前关掉 Key 配置做一次错误演练，观察 `error` 帧和历史是否变化。
- **参考**：[FastAPI async](https://fastapi.tiangolo.com/async/)、[OpenRouter Streaming](https://openrouter.ai/docs/api/reference/streaming)、[MDN ReadableStream](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream)。

## Day 5 · Redis、Celery 和轮询

- **必须掌握**：Cache Aside、TTL、Broker/Producer/Worker、业务状态与投递状态的区别、有限重试。异步 I/O 在当前请求内让出执行权，后台任务可等请求返回后由其他进程继续。
- **必读文件与函数**：`main.py::upload_document` 或 `agent_task` 接收请求。`tasks.py::submit_job` 先向 PostgreSQL 写 PENDING，再 `apply_async` 将 Job ID 放进 Redis DB 1。`tasks.py::execute_job` 定义 Celery 注册的任务，从队列接收并执行。`finish_job` 更新数据库。`frontend/src/pages/Tasks.vue::poll` 与 `refresh` 每 2.5 秒调 `GET /tasks`，不足时再请求详情。
- **缓存链路**：`llm.py::get_model` 查 Redis DB 0，Miss 时读 PostgreSQL 并 `setex`；`main.py::edit_model` 写库提交后调用 `invalidate_model`。
- **可跳过**：Celery 的底层消息格式，prefork 内部实现。
- **独立练习**：在知识库上传小文件，记录 Job ID、任务表和 Worker 日志。修改 TTL 为 10 秒，前后两次读取并用 redis-cli 看倒计时。
- **参考**：[Celery First Steps](https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html)、[Celery Retry](https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying)、[Redis TTL](https://redis.io/docs/latest/commands/ttl/)。

## Day 6 · 知识库和文档分析 Agent

- **必须掌握**：Chunking、Embedding、相似度、两种检索、RAG 注入证据、工具 JSON Schema、最大轮数。
- **必读文件与函数**：`knowledge.py::chunk_text`、`build_index`、`retrieve`。`chat.py::lookup` 把片段反馈进 prompt。`tasks.py::run_agent`、`call_tool` 负责发工具说明、解析模型返回、在当前用户范围执行，再把结果交回模型。
- **可跳过**：Sentence Transformers 内部架构、FAISS 序列化细节、脚本中的命令行解析。
- **独立练习**：找一道中英文表现不同的评测题。对照命中的文档和实际证据行，修改查询或分块大小，在新的测试库上重建索引再比较。然后给 Agent 传无效 ID，理解工具错误如何返回模型。
- **参考**：[Sentence Transformers 语义检索](https://sbert.net/examples/sentence_transformer/applications/semantic-search/README.html)、[FAISS metric](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances)、[OpenRouter Tool Calling](https://openrouter.ai/docs/guides/features/tool-calling)。

## Day 7 · 测试、日志与部署

- **必须掌握**：Docker Compose 服务 DNS、健康检查、共享卷、一条 request ID 的排查链路、单测／真实集成测试边界。
- **必读文件与函数**：`docker-compose.yml`、两个 Dockerfile、`frontend/nginx.conf`、`common.py::record_call`、`main.py::add_request_id`、`tests/test_platform.py` 中三个你要现场讲的用例。
- **可跳过**：依赖锁文件细节、Nginx 内部事件机制。
- **独立练习**：关闭 Worker 后提交任务，再恢复 Worker 观察状态变化。在后台用 request ID 筛任务和模型日志。用 [验收记录](docs/VERIFICATION.md) 对比自己的 Windows 实测。
- **参考**：[Docker Compose 网络](https://docs.docker.com/compose/how-tos/networking/)、[pytest fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html)、[Python logging](https://docs.python.org/3/howto/logging.html)。
