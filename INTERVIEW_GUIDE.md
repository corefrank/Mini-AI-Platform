# 面试指南

## 一分钟介绍

我做了一个开发文档知识库和智能体管理平台。前端用 Vue 3，后端用 FastAPI 和 PostgreSQL。用户上传文档后，API 先保存文档和任务记录，再用 Redis 将任务交给 Celery Worker。Worker 生成 CPU Embedding 并构建 FAISS 索引。用户可在浏览器检索文档，切换大模型进行流式问答，或者提交文档分析 Agent。平台在后端做 JWT、角色和资源归属校验，用 Redis 缓存模型配置，并用 request ID 串起模型与任务日志。我重点验证了浏览器接口、异步任务、数据隔离和真实索引，同时记录了真实上游模型的验收边界。

## 架构怎么讲

先用一句话走完 `Vue → FastAPI → PostgreSQL → Redis → Celery → PostgreSQL → Vue`。当面试官问 AI，再展开两条路径。聊天以 SSE 消费上游文本流，结束时持久化。Agent 以后台任务调用模型，由模型选择只读工具，工具实际执行并返回证据，最终把报告写进 Job。两条路径共享当前用户的数据、模型配置接口和 request ID 日志。前端同源路径由 Nginx 或 Vite 转发。可对照 [架构图](README.md#架构)。

## 选型和常见追问

| 技术与典型提问 | 项目里的回答 | 代码 |
| --- | --- | --- |
| FastAPI 和 Flask 有什么区别？ | FastAPI 基于 ASGI，提供类型驱动的参数校验、依赖注入和 OpenAPI。Flask 是轻量 WSGI 框架，许多功能可由扩展补齐。这里选择 FastAPI 简化接口校验和异步流。 | `main.py`、`schemas.py` |
| REST API 如何设计？ | `GET /conversations/{id}` 读取，`PATCH` 改标题，`DELETE` 删除，POST 创建返回 201。文档异步处理返回 202 和 Job ID，客户端单独查询。 | `chat.py`、`main.py` |
| 什么会触发 CORS 预检？ | 跨源发带 Authorization 的请求通常会先发 OPTIONS。当前部署通过同源代理，也提供指定开发源的 CORS 配置。 | `main.py`、`nginx.conf` |
| ORM 与原生 SQL 如何取舍？ | CRUD 用 SQLAlchemy 模型、Session 和 select，避免重复映射。复杂聚合可用参数化 SQL，当前 `SELECT 1` 是健康检查。ORM 仍会发 SQL。 | `db.py`、`main.health` |
| JWT、角色、归属分别解决什么？ | JWT 签名认证身份，数据库角色决定能否访问后台，归属决定能否读具体对象。JWT 载荷可读取，只放 ID 和时效等元数据。 | `common.py` |
| async/await 为什么能提高 I/O 并发？ | 等待上游网络数据时协程把执行权交还事件循环。同步数据库与检索放到线程池，避免在 SSE 协程里直接执行阻塞操作。 | `chat.chat_stream`、`llm.stream_once` |
| SSE 与 WebSocket 有何区别？ | SSE 是经 HTTP 的服务端单向事件流。交互只需客户端 POST 和服务端增量回传，SSE 足够。Fetch 读取 POST 流可传 JWT Header。WebSocket 更适合持续双向消息。 | `api.js`、`sse.js` |
| SSE 出错与断开怎样处理？ | 首帧之前可回 HTTP 错误；已开始后的错误走 `event: error`。客户端用 AbortController 停止。历史在上游正常结束、两条消息提交后才发 done。 | `Chat.vue`、`chat.py` |
| Redis 缓存怎么做？ | Cache Aside。Miss 时读 PostgreSQL 并设 60 秒 TTL，管理员更新后删除键。Redis 暂不可用时读取可回数据库。并发读回填旧值的窗口以 TTL 兜底。 | `llm.get_model`、`main.edit_model` |
| Celery Broker、Worker 和 Task 的作用？ | API 是 Producer，Broker 传 Job ID，Worker 执行注册的任务，业务状态落 PostgreSQL。投递确认和任务成功是不同阶段。Index 通过原子替换发布。 | `tasks.py` |
| 异步 I/O 与后台任务怎么区分？ | 聊天等待上游时释放事件循环，浏览器还维持连接。上传和分析可以先返回 202，等待 Worker 异步工作并轮询。 | `chat.py`、`tasks.submit_job` |
| RAG、Embedding、FAISS 什么关系？ | Embedding 把问题与片段编码为向量。FAISS 对单位化向量做精确内积检索。RAG 把检索片段放进模型输入并在答案旁展示来源。BM25 提供单独词项基线。 | `knowledge.py`、`chat.lookup` |
| Function Calling 会自行执行代码吗？ | 模型生成工具名和参数。后端用固定 Schema 验证后执行允许的只读函数，再把结果回传给模型。限制轮数和每轮调用数。 | `tasks.run_agent`、`tasks.call_tool` |
| Compose 为什么用服务名连接？ | 同一个 Compose 默认网络内服务名可解析。API 找 db 和 redis，Nginx 找 api。PostgreSQL、Redis、索引和模型缓存用命名卷。 | `docker-compose.yml`、`nginx.conf` |
| 日志该记录什么？ | request ID、用户 ID、模型／任务、时间、耗时、状态、受控异常、实际 Token 统计。凭据、提示原文和供应商响应体不写日志。 | `common.record_call`、`main.logs` |
| 事务怎么用？ | 一轮问答成对写入和修订号递增由同一个事务提交。任务状态及文档状态也同事务更新。Redis 发布是独立系统操作，要说明现有窗口。 | `chat.save_turn`、`tasks.finish_job` |
| 为什么为 user_id 建索引？ | 经常按归属过滤会话、文档和任务。索引提高适当查询效率，也增加写入与存储开销。应结合查询计划评估。 | `db.py` |
| Engine 和 Session 有什么区别？ | Engine 管连接池和方言。Session 管工作单元和事务。每次数据库操作使用短生命周期 Session，模型推理期间不占数据库事务。 | `db.py`、`chat.prepare_turn` |
| 为什么只用一名 Worker？ | 串行索引更新容易理解，个人项目数据量可控。后台任务是独立进程，分开 API 等待与 CPU 计算。后续扩展需补幂等、队列和恢复策略。 | `docker-compose.yml`、`tasks.py` |

表内后端文件位于 `backend/app/`，组件位于 `frontend/src/`。

## 简历参考

**轻量级 AI 技术知识库与智能体管理平台**｜FastAPI、Vue 3、PostgreSQL、Redis、Celery、FAISS

- 开发 AI 对话、知识库、任务中心和系统管理界面，使用 REST API、JWT 与资源归属校验管理多用户会话、文档和后台任务。
- 使用 Redis Broker 与 Celery Worker 异步处理文档分块和 CPU Embedding，构建隔离的 FAISS 索引。导入 80 篇官方技术文档，准备 30 道检索评测题并对比向量与 BM25。
- 实现 OpenRouter 统一调用、POST SSE、文档分析工具调用和请求级日志。使用 pytest 验证流式响应、跨用户访问和 Agent 工具链路。

若面试官问是否调用过真实模型，按自己的 `smoke-openrouter` 实测回答。课程项目规模适合讲架构和工程取舍，吞吐、故障率和生产部署需要实际数据再写。
