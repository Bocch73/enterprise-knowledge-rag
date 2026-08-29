# 技术栈与职责

本文件说明“为什么需要这个组件”，不等同于立即安装。具体依赖版本会在首次使用时锁定，并由自动化更新工具提出升级，而不是使用无限制的最新版。

| 层次 | 技术 | 职责 | 选择理由 | 主要风险 |
|---|---|---|---|---|
| 后端语言 | Python 3.11 | 接口、文档处理、检索和评测 | 人工智能与文档处理生态完整；本机已验证 | 需要严格类型和测试弥补动态语言错误 |
| 接口框架 | FastAPI | HTTP 接口、参数验证、OpenAPI 文档 | 类型驱动，自动生成接口规范，支持依赖注入 | 错误使用异步代码可能阻塞事件循环 |
| 数据访问 | SQLAlchemy 2 | Python 对数据库的统一访问 | 显式事务、成熟映射和测试生态 | 仍需理解 SQL，不能依赖工具隐藏查询问题 |
| 数据库迁移 | Alembic | 版本化修改数据库结构 | 可重复升级和回滚结构 | 自动生成迁移必须人工审查 |
| 主数据库 | PostgreSQL 17 | 关系数据、事务、全文检索 | 成熟、可扩展，支持结构化与文本查询 | 本机安装和备份需要运维知识 |
| 向量扩展 | pgvector 0.8 系列 | 保存向量、相似度查询和近似索引 | 向量与权限元数据在同一数据库查询 | 索引参数会影响速度和召回率 |
| 本地缓存与限流 | Python 进程内有界状态 | 向量缓存和请求频率保护 | Windows 本地无需新增服务，接口可替换 | 不能跨实例共享，重启后清空 |
| 生产缓存与消息 | Redis（计划） | 共享缓存、限流计数、任务代理和结果状态 | 速度快，支持原子操作，Celery 支持成熟 | 不是业务数据唯一可信来源 |
| 当前后台任务 | PostgreSQL 任务表 + Python 持续工作进程 | 文档解析、向量生成和索引任务 | Windows 与单机 Linux 均可运行，数据库保留最终状态 | 轮询延迟，不适合大规模任务吞吐 |
| 目标后台任务 | Redis + Celery（计划） | 多实例任务通知、执行和重试 | 支持成熟的任务队列与监控 | 官方不支持 Windows 原生工作进程，增加运维复杂度 |
| 前端 | Vue 3.5.42 + TypeScript 6.0 | 企业工作台和对话页面 | 组件化、类型支持和成熟官方生态 | 状态管理失控时页面逻辑会复杂 |
| 前端构建 | Vite 8.2.2 | 本地开发代理和生产构建 | Vue 官方工具链常用，启动反馈快 | 开发服务器不能作为生产入口 |
| 前端状态 | Pinia 4.0.3 | 登录会话和跨页面状态 | Vue 官方生态中的状态管理方案 | 不应把服务器真相长期复制到浏览器 |
| 后端测试 | pytest | 单元、集成和接口测试 | Python 生态成熟，夹具表达清晰 | 测试替身不能代替真实数据库测试 |
| 代码质量 | Ruff + mypy | 代码规则、格式和静态类型检查 | 快速、可自动化 | 检查通过不等于业务逻辑正确 |
| 前端测试 | Vitest 4.1.11 + Playwright 1.62.1 | 组件测试和浏览器端到端测试 | 覆盖组件逻辑与真实用户流程 | 浏览器测试成本高，应聚焦关键流程 |
| 运行指标 | prometheus-client 0.26.0 | 暴露请求、检索、模型和任务指标 | 官方 Python 客户端，格式可接入 Prometheus | 高基数标签或多进程配置错误会增加成本 |
| 分布式追踪 | OpenTelemetry（计划） | 跨服务请求追踪 | 使用开放标准，降低监控供应商绑定 | 采样和敏感字段设计不当会增加风险 |
| 持续集成 | GitHub Actions | 后端、前端、浏览器、RAG 质量和镜像门禁 | 可复用工作流和临时依赖环境 | 尚未推送远程仓库，暂无真实运行记录 |
| 镜像构建 | Docker 多阶段构建 | 生成可追溯的前后端运行制品 | 构建与运行依赖分离，支持非根用户 | 本机未安装 Docker，当前只做静态验证 |
| 单机编排 | Docker Compose | 数据库、迁移、接口、工作进程和前端顺序 | 适合预发布和单机演示 | 不等同于多实例高可用编排 |
| 反向代理 | Nginx 1.28.3 | 静态文件、同源接口代理和事件流 | 成熟、资源占用低 | 正式公网仍需 HTTPS 入口和证书管理 |

## 关键技术解释

- **OpenAPI**：一种描述 HTTP 接口路径、参数、响应和认证方式的开放规范，可用于生成交互文档和客户端代码。
- **依赖注入**：由框架把数据库会话、当前用户等依赖提供给业务函数，减少函数自行创建全局对象。
- **对象关系映射**（Object-Relational Mapping）：把 Python 对象与关系数据库表关联的技术，常简称 ORM。
- **事件循环**：异步程序协调多个等待操作的执行机制；如果在其中执行长时间阻塞任务，会拖慢所有请求。
- **近似索引**：通过允许少量召回损失换取更快搜索的向量索引；必须用真实数据评测速度和召回率。
- **夹具**：测试运行前准备数据和依赖、运行后清理的可复用机制。
- **端到端测试**：从浏览器入口到后端和数据层验证完整用户流程的测试。
- **请求追踪**：用关联标识记录一次请求跨越多个模块的耗时和结果。
- **指标采集**：监控服务定时访问应用的指标端点并保存时间序列；本项目当前只实现端点，尚未部署监控服务。
- **高基数标签**：标签值数量非常多的指标设计，例如把用户编号作为标签，会增加监控资源消耗和泄露风险。
- **持续交付**：质量门禁通过后自动产生随时可部署的制品，但生产推广仍保留明确批准。
- **多阶段构建**：使用一个镜像阶段安装或编译，再把运行所需内容复制到更小的最终阶段。
- **镜像摘要**：由镜像内容计算的不可变标识，比可能移动的标签更适合精确发布和回滚。

## 资料依据

- [FastAPI 功能与开放标准](https://fastapi.tiangolo.com/features/)
- [SQLAlchemy 2 对象关系映射入门](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
- [PostgreSQL 全文检索类型](https://www.postgresql.org/docs/current/datatype-textsearch.html)
- [pgvector 官方项目](https://github.com/pgvector/pgvector)
- [Celery 任务队列说明](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)
- [Redis 开发文档](https://redis.io/docs/latest/develop/)
- [Vue 3 官方指南](https://vuejs.org/guide/introduction.html)
- [Prometheus Python 客户端指标类型](https://prometheus.github.io/client_python/instrumenting/)
- [Prometheus Python 客户端多进程模式](https://prometheus.github.io/client_python/multiprocess/)
- [GitHub Actions PostgreSQL 服务容器](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)
- [Dockerfile 参考](https://docs.docker.com/reference/dockerfile)
- [PostgreSQL 17 备份与恢复](https://www.postgresql.org/docs/17/backup-dump.html)
