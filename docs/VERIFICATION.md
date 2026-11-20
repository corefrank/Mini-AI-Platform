# 验收记录

## 本次已实测

| 检查 | 结果与边界 |
| --- | --- |
| 依赖和运行 | uv 锁文件解析、Linux Python 3.12 CPU 依赖同步成功。FastAPI 启动并通过真实 PostgreSQL 17.12 的健康检查 |
| 后端测试 | SQLite 和独立 PostgreSQL 测试库分别 8/8 通过。SSE 成功响应及工具调用用 Mock，缓存单测用测试替代对象 |
| 前端测试 | Vite 生产构建成功。Node SSE 测试 2/2 通过，覆盖 UTF-8 分段、正常结束、错误和意外断开 |
| HTTP 联调 | 使用实际 Vite 代理访问 FastAPI，验证登录、Admin/User、跨用户 404、文档和任务读取 |
| 真实队列与入库 | Redis 7.0.15 Broker、Celery 5.6.3 prefork Worker。固定版本官方语料下载 80/80，实际上传后 READY 80/80，失败 0 |
| 真实检索 | CPU MiniLM 成功生成 384 维向量。FAISS 建盘并按真实内容搜索，BM25 可用。Bob 的知识库无 Alice 的文档和索引结果 |
| 真实缓存 | Redis 键实际经 Miss 回写、Hit、TTL、Admin 更新后删除及下次请求回填 |
| 缺少 API Key | 真实 HTTP SSE 返回受控错误，无半轮历史。Agent 经过真实队列执行后在 PostgreSQL 显示 FAILED，尝试 1 次 |
| 混合集成验证 | FastAPI、PostgreSQL、Redis、Celery、Vite 和 FAISS 均真实运行，上游使用本机 HTTP 模拟服务。两份模型配置各输出 2 个 delta，RAG 返回证据，历史保存 6 条消息。Agent 上游第一次响应 503，真实 Worker 第二次执行完成工具调用并保存报告和轨迹。另实测客户端关闭 SSE，日志为 DISCONNECTED 且无半轮历史 |
| Compose | Docker Compose v2.39.4 成功解析配置并列出 api、frontend、worker、db、redis 五个服务 |

测试使用 Linux 进程连接真实服务。由于环境禁止 Unix Socket，Docker 的 containerd 无法启动，Chromium 也在启动阶段退出。Vite 代理级 HTTP 验证和前端构建均已通过。

## 检索结果

语料为完整的 80 篇。每种语言 27 道可答题，另有 3 道无证据题用来手工检查。指标按文档级参考证据计算，候选为排名前 5 个片段。

| 查询语言 | 方法 | Recall@5 | Hit@5 |
| --- | --- | ---: | ---: |
| 英文 | MiniLM + FAISS | 96.30% | 100.00% |
| 英文 | BM25 | 98.15% | 100.00% |
| 中文 | MiniLM + FAISS | 77.78% | 81.48% |
| 中文 | BM25 | 88.89% | 92.59% |

逐题结果在 [英文 JSON](../data/evaluation/results-en.json) 和 [中文 JSON](../data/evaluation/results-zh.json)。这是小样本基线，题目常保留英文技术名词，BM25 可以直接命中。不能由此推断其他语料的排序效果或 RAG 答案正确率。证据位置用固定语料逐项核对。

## 尚未验证与 Windows 验收

1. **Docker Desktop 完整栈**。在本地启动 Docker Desktop，按 [README](../README.md) 配置 `.env`，执行 `docker compose config --quiet`、`docker compose up -d --build --wait`、`docker compose ps`。检查健康接口和 `docker compose logs --tail=50 worker`。完成数据导入后到任务中心检查 SUCCESS，重启栈确认历史和索引仍可访问。
2. **Chromium 中操作五个页面**。打开 `http://127.0.0.1:8080`，用 alice 创建或重命名会话，上传、检索并查看任务。用 bob 确认数据隔离，用 admin 确认三个管理 Tabs。开启开发者工具观察增量帧和停止按钮。
3. **真实 OpenRouter 推理**。把自己的 Key 填入 `.env`，用 `docker compose up -d api worker` 使配置生效。Alice 导入语料后执行 `uv run --project backend python scripts/platform_cli.py smoke-openrouter`，检查两种模型、带来源的 RAG、六条持久化消息和 Agent 报告。然后按任务 Request ID 检查后台日志。真实账户额度、模型响应质量和实际 Token 值需本地确认。
4. **无证据题回答与人工引用校验**。在同一知识库中手工发这三道题，检查模型是否明确说证据不足。对两道跨文档题核对每处引文与官方片段。检索评测本身没有对生成文本做评分。
