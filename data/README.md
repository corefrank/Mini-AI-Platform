# 技术语料与评测

[sources.json](sources.json) 记录六个官方仓库的 Git commit、许可 URL、每篇文档 ID、标题、原文件路径和官网地址。

| 类别 | 数量 | 源文件位置 | 文档许可 |
| --- | ---: | --- | --- |
| FastAPI | 20 | fastapi/fastapi 的 docs/en/docs/ | MIT，仓库文本 |
| Vue | 15 | vuejs/docs 的 src/guide/ | CC BY 4.0，图片除外 |
| Redis | 15 | redis/docs 的 content/commands/ | CC BY-NC-SA 4.0，部分旧内容有 CC BY-SA 4.0 例外 |
| Celery | 10 | celery/celery 的 docs/ | 文档 CC BY-SA 4.0，软件 BSD-3-Clause |
| Docker | 10 | docker/docs 的 content/manuals/ | 仓库文本 Apache-2.0 |
| LangGraph | 10 | langchain-ai/docs 的 src/oss/langgraph/ | 仓库文本 MIT |

下载脚本保存 UTF-8 文本，删除 YAML front matter 及部分 MDX 包装，RST 原样保存至 TXT。图片和外链资源不下载。项目发布包只有脚本与清单，生成文档供本机使用。另行发布语料时按每个来源的实际许可处理。

[evaluation/questions.json](evaluation/questions.json) 含 30 道手工编写的双语题，27 道可答、3 道无证据。每个参考项给出语料来源 ID、定位文本、本地文本行号和官网地址。

`evaluate` 对同一语料分别检索向量和 BM25。Recall@5 是每题前 5 个片段中命中的参考文档数 / 该题参考文档总数，再对 27 道可答题平均。Hit@5 只看是否至少命中一篇。无证据题输出候选用于人工复核，不进入分母。两种语言分别评测。
