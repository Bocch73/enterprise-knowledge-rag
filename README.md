# Enterprise Knowledge RAG

一个用于求职面试展示的企业级知识库问答系统。项目会从零实现文档上传、解析、分块、检索、生成带来源引用的答案、权限控制、质量评测、监控和部署。

> 当前阶段：第 14 步已完成。系统已经形成从需求、架构、实现、测试、评测、安全交付到面试答辩的完整证据链。本机仍未安装 Docker，也没有远程仓库或生产服务器，因此容器和流水线不能声称已经在线运行。

## 为什么做这个项目

企业内部的制度、产品说明、操作手册往往分散在多个文档中，员工查找答案慢，而且普通大语言模型无法可靠访问这些私有资料。本项目通过“检索增强生成”先查找相关原文，再让大语言模型依据原文回答，并展示引用来源。

## 学习方式

本项目按企业软件开发流程逐步完成。每一步都包含：

1. 本步目标和业务原因。
2. 新名词的完整解释。
3. 实际文件或代码改动。
4. 可重复的验证方法。
5. 知识点总结。
6. 官方文档链接。
7. 面试题与参考答案。

详细路线见 [学习与开发路线](docs/00-learning-roadmap.md)，当前项目边界见 [项目章程](docs/01-project-charter.md)，功能范围见 [功能需求](docs/requirements/functional-requirements.md)，整体设计见 [系统架构](docs/architecture/system-architecture.md)，后端基础见 [第 4 步教程](docs/04-backend-foundation.md)，数据库与权限见 [第 5 步教程](docs/05-database-and-authorization.md)，文档上传与解析见 [第 6 步教程](docs/06-document-ingestion.md)，分块与向量写入见 [第 7 步教程](docs/07-chunking-and-vector-indexing.md)，混合检索见 [第 8 步教程](docs/08-hybrid-retrieval.md)，DeepSeek 带引用问答见 [第 9 步教程](docs/09-grounded-answers.md)，Vue 工作台见 [第 10 步教程](docs/10-frontend-workbench.md)，质量评测见 [第 11 步教程](docs/11-quality-evaluation.md)，企业级运行时加固见 [第 12 步教程](docs/12-enterprise-hardening.md)，持续集成与部署见 [第 13 步教程](docs/13-continuous-integration-and-deployment.md)，面试交付方法见 [第 14 步教程](docs/14-interview-delivery.md)，可直接使用的演示与简历材料见 [面试交付索引](docs/delivery/README.md)，开发规则见 [贡献指南](CONTRIBUTING.md)，新名词见 [术语表](docs/glossary.md)。

## 当前可运行接口

进入 `backend` 目录并激活虚拟环境后运行：

```powershell
.\.venv\Scripts\python.exe -m app.server --reload
```

- 接口交互页面：<http://127.0.0.1:8000/docs>
- 存活检查：<http://127.0.0.1:8000/api/v1/health/live>
- 就绪检查：<http://127.0.0.1:8000/api/v1/health/ready>
- 用户注册：`POST /api/v1/auth/register`
- 用户登录：`POST /api/v1/auth/login`
- 当前用户：`GET /api/v1/auth/me`
- 知识库：`/api/v1/knowledge-bases`
- 文档上传：`POST /api/v1/knowledge-bases/{id}/documents`
- 文档与版本：`/api/v1/documents`
- 摄取任务：`/api/v1/ingestion-jobs`
- 文档片段：`GET /api/v1/documents/versions/{version_id}/chunks`
- 混合检索：`POST /api/v1/knowledge-bases/{id}/search`
- 带引用回答：`POST /api/v1/knowledge-bases/{id}/answers`
- 校验后流式回答：`POST /api/v1/knowledge-bases/{id}/answers/stream`
- Prometheus 指标：`GET /metrics`
- 管理员审计查询：`GET /api/v1/admin/audit-events`
- 管理员摄取队列：`GET /api/v1/admin/ingestion-jobs`

应用连接本机 PostgreSQL 17.11，不依赖 Docker，也不会访问本机已有的 SQL Server 或 MySQL。首次使用管理员功能前，按 [第 5 步教程](docs/05-database-and-authorization.md)运行交互式管理员引导命令。上传后在第二个终端运行本地工作进程：

```powershell
.\.venv\Scripts\python.exe -m app.cli.process_ingestion_jobs --max-jobs 10
```

完整上传顺序见 [第 6 步教程](docs/06-document-ingestion.md)，分块与向量验证见 [第 7 步教程](docs/07-chunking-and-vector-indexing.md)，混合检索操作见 [第 8 步教程](docs/08-hybrid-retrieval.md)，真实模型问答见 [第 9 步教程](docs/09-grounded-answers.md)。

## 前端工作台

后端启动后，在项目根目录的第二个终端运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

打开 <http://127.0.0.1:5173>。上传文档后仍需在第三个终端运行文档处理工作进程。完整操作和测试命令见 [第 10 步教程](docs/10-frontend-workbench.md)。

## 质量评测

运行免费的隔离检索参考实验：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-reference-evaluation.ps1
```

运行不向外部服务发送数据的确定性完整链路实验：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-reference-evaluation.ps1 -Mode full -GenerationProvider deterministic
```

评测集、虚构语料和真实生成的 JSON 报告位于 `evaluation` 目录。五个虚构问题的 `deepseek-v4-flash` 真实实验已经通过质量门禁；指标公式、逐题结果、结论边界和数据安全要求见 [第 11 步教程](docs/11-quality-evaluation.md)。

## 企业级运行保护

本地默认启用 60 秒固定窗口限流和 300 秒向量缓存。认证、回答生成与普通业务接口使用不同上限；
关键操作写入 PostgreSQL 审计表。`/metrics` 本机默认可访问，非本地环境必须配置独立监控令牌并限制
网络入口。当前限流和缓存只适合单进程，多实例部署前必须迁移到 Redis 等共享实现。配置、验证方式和
生产边界见 [第 12 步教程](docs/12-enterprise-hardening.md)。

## 持续集成与安全交付

拉取请求和主分支变更会执行后端、前端、浏览器、真实 PostgreSQL 集成测试、确定性 RAG 评测和镜像
构建。版本标签在重新通过同一套门禁后发布前后端镜像。部署采用独立迁移任务、内部数据库网络、文件型
密钥、非根用户、只读文件系统和明确回滚清单。当前没有远程仓库、Docker 或生产服务器，因此工作流和
镜像只完成本地静态验证，不能声称已经生产上线。详见
[第 13 步教程](docs/13-continuous-integration-and-deployment.md)和
[部署运行手册](docs/operations/deployment-runbook.md)。

## 面试交付

先阅读[简历描述与自我介绍](docs/delivery/resume-and-introduction.md)，再按照
[10 至 15 分钟演示脚本](docs/delivery/demo-script.md)排练。面试前运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-interview-delivery.ps1
```

该检查不会启动 Docker，也不会调用 DeepSeek。架构追问见[架构答辩手册](docs/delivery/architecture-defense.md)，
完整题库见[综合项目答辩](docs/interview/14-project-defense.md)。

## 参考项目

- [Jsjsnc/knowledge-base-rag](https://github.com/Jsjsnc/knowledge-base-rag)：重点参考企业能力清单、评测证据和工程闭环。
- [RAGFlow](https://github.com/infiniflow/ragflow)：重点参考复杂文档处理和知识库产品能力。
- [Dify](https://github.com/langgenius/dify)：重点参考工作流、模型适配和产品化思路。
- [Haystack RAG App](https://github.com/deepset-ai/haystack-rag-app)：重点参考较小规模的前后端示例。

参考不等于复制。本项目会保留独立的需求、架构决策、提交历史、测试结果和评测数据，确保面试时每一部分都能讲清楚。
