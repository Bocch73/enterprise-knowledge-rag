# 第 13 步：持续集成、持续交付与安全部署

## 1. 本步目标

前十二步证明了项目功能、质量和运行保护。本步把“开发者电脑上检查通过”升级为“每次变更都由统一
流水线检查，并能产生可追溯、可回滚的发布制品”。

本步交付：

1. 可复用 GitHub Actions 质量门禁。
2. PostgreSQL 17 与 pgvector 0.8.6 的临时集成测试环境。
3. 后端、前端、浏览器流程和确定性 RAG 评测。
4. 前后端多阶段容器镜像与非根用户运行。
5. 单机生产式 Compose 拓扑、独立迁移任务和持久卷。
6. 文件型密钥、内部数据库网络、健康检查和日志轮转。
7. PostgreSQL 备份与安全恢复演练脚本。
8. 发布、验证、停止和回滚检查清单。

你的电脑仍然不需要安装 Docker。代码推送到 GitHub 后，由 GitHub 托管的 Linux 执行器实际运行测试
与构建；本机继续保留不依赖 Docker 的静态验证路径。

## 2. 新名词解释

### 2.1 持续集成

**持续集成**（Continuous Integration）表示开发者频繁合并小改动，每次变更都自动执行构建、测试、
格式、类型和安全检查，常简称 CI。它的重点不是“自动”，而是尽早发现不同模块组合后的问题。

### 2.2 持续交付与持续部署

- **持续交付**（Continuous Delivery）：质量门禁通过后自动生成随时可以部署的制品，但生产上线仍需
  明确批准。
- **持续部署**（Continuous Deployment）：门禁通过后自动上线生产，不保留人工批准。

本项目采用持续交付。当前没有授权的生产服务器，自动修改外部环境既不安全也不能提供真实价值。

### 2.3 工作流、任务、步骤和执行器

- **工作流**（Workflow）：一份 YAML 自动化定义。
- **任务**（Job）：工作流中可以独立运行的一组步骤。
- **步骤**（Step）：检出代码、安装依赖或运行测试等一个动作。
- **执行器**（Runner）：真正执行任务的机器。本项目使用 GitHub 托管的 Ubuntu Linux 执行器。

任务可以并行，例如后端和前端检查同时进行；镜像构建必须等待它们成功。

### 2.4 服务容器

服务容器是在一个流水线任务期间临时启动的数据库或缓存。GitHub 在任务结束后销毁它，所以不会污染
你的本地数据库。本项目用 `pgvector/pgvector:0.8.6-pg17-bookworm` 创建 `rag1_test`，只放 CI
测试数据。

### 2.5 制品、镜像、镜像仓库和摘要

- **制品**（Artifact）：流水线产生并保留的结果，例如覆盖率文件、评测报告或容器镜像。
- **容器镜像**：包含应用代码、运行时和依赖的只读分层包。
- **镜像仓库**（Registry）：保存和分发镜像的服务，本项目计划使用 GitHub Container Registry。
- **镜像摘要**（Digest）：根据镜像内容计算的不可变标识。标签可能移动，摘要指向精确内容。

### 2.6 多阶段构建

多阶段 Dockerfile 使用一个阶段安装或编译依赖，再把运行所需内容复制到更小的最终阶段。前端使用
Node.js 构建静态文件，最终镜像只保留 Nginx 和 `dist`；后端也把依赖构建与运行阶段分开。

### 2.7 软件物料清单与构建来源证明

**软件物料清单**（Software Bill of Materials）列出镜像中包含的软件组件，常简称 SBOM。
**构建来源证明**（Provenance）描述制品由哪个源代码和构建过程产生。发布工作流要求 BuildKit 为镜像
生成这两类供应链证据。

### 2.8 发布、推广和回滚

- **发布**：产生一个带版本的制品。
- **推广**：让同一个制品依次进入预发布和生产，而不是每个环境重新构建。
- **回滚**：发生严重问题时恢复到上一个已验证版本。

数据库回滚和应用回滚不是同一件事。旧镜像通常容易恢复，数据库降级可能丢数据，不能默认自动执行。

## 3. 企业流水线

```text
拉取请求 / main 推送
          │
          v
  可复用质量门禁
    ├── 后端：PostgreSQL + pgvector + 代码检查 + 96 以上测试
    ├── 前端：格式 + 类型 + 单元测试 + 构建 + 浏览器流程
    ├── RAG：隔离语料 + 确定性完整链路质量门禁
    └── 镜像：前后端 Docker 构建但不发布
          │
          v
      允许合并

v0.2.0 等版本标签
          │
          v
  再次执行同一套门禁
          │
          v
  发布带 SBOM 和来源证明的前后端镜像
          │
          v
  预发布验证 → 人工批准 → 生产推广
```

可复用工作流位于 `.github/workflows/quality-gates.yml`。普通持续集成和版本发布都调用它，避免“拉取
请求检查一套，发布时却跑另一套”的漂移。

## 4. 后端门禁

后端任务使用临时 PostgreSQL 17 + pgvector 0.8.6，并完成：

- 从 `requirements-dev.lock` 安装固定依赖；
- 运行全部测试和分支覆盖率门槛；
- 运行 Alembic 数据库结构漂移检查；
- 运行 Ruff 代码规范与格式检查；
- 运行 Mypy 严格类型检查；
- 上传 `coverage.xml`，保留 14 天。

CI 数据库密码和 JSON 网络令牌密钥是只存在于临时执行器的测试值，不是生产密钥。工作流没有
`DEEPSEEK_API_KEY`，所以拉取请求不可能意外产生模型费用或发送文档。

## 5. 前端门禁

前端任务执行：

- `npm ci` 按 `package-lock.json` 精确安装依赖；
- Prettier 格式检查；
- Oxlint 与 ESLint 代码检查；
- Vue 与 TypeScript 类型检查；
- Vitest 单元测试与覆盖率；
- Vite 生产构建；
- Playwright Chromium 浏览器验收。

本机仍使用已经安装的 Google Chrome；Linux CI 使用 Playwright 管理的 Chromium。浏览器验收拦截后端
请求并使用虚构数据，因此不依赖 DeepSeek 或开发数据库。

## 6. RAG 质量门禁

独立任务重新创建 `rag1_test`，上传三份虚构制度文件，执行解析、分块、向量写入、检索、确定性回答、
引用校验和拒答，再生成 JSON 报告。

它不用外部模型，因此结果稳定、免费且可以运行在每个拉取请求上。真实 DeepSeek 基准线仍保留为人工
批准的周期实验，不应在每次代码提交时发送数据和产生费用。

## 7. GitHub Actions 安全控制

本项目当前采取：

1. 默认 `contents: read`，工作流令牌只读源码。
2. 只有发布镜像的任务获得 `packages: write`。
3. 不使用 `pull_request_target` 执行来自分支的代码，降低高权限令牌泄露风险。
4. 不把生产密钥传给拉取请求。
5. 使用并发组取消同一分支的旧 CI，节省时间；发布任务不自动取消。
6. 使用 Dependabot 每周检查 Python、Node.js、GitHub Actions 和基础镜像更新。
7. 发布前重新运行全部质量门禁。

工作流目前使用官方动作的主版本标签，并由 Dependabot维护。更高安全环境应进一步把第三方动作固定到
完整提交哈希，并由安全团队审查升级。

## 8. 版本发布

`.github/workflows/release.yml` 只响应 `v*.*.*` 版本标签。版本号采用语义化版本：

- 主版本：存在不兼容变化；
- 次版本：向后兼容的新功能；
- 修订版本：向后兼容的问题修复。

发布工作流不会直接登录服务器。它重新运行质量门禁，然后向 `ghcr.io/<仓库>/<backend|frontend>`
发布镜像，并写入版本、代码修订号、软件物料清单和来源证明。

持续集成工作流已经由主分支推送真实触发。发布工作流只有创建符合规则的版本标签才会运行；当前没有
发布版本标签，因此不能声称已经向容器镜像仓库发布镜像。

## 9. 容器安全

后端和前端镜像均：

- 使用明确的 Python、Node.js 和 Nginx 版本；
- 使用多阶段构建；
- 通过 `.dockerignore` 排除密钥、虚拟环境、测试输出和本地数据；
- 使用固定的非根用户运行；
- 包含健康检查；
- 最终容器以只读文件系统运行，只有 `/tmp` 和持久数据卷可写；
- 删除 Linux capabilities 并启用 `no-new-privileges`。

**Linux capability** 是从传统 root 权限拆分出的细粒度系统能力。应用不需要修改网络、挂载文件系统等
特权，因此运行时删除全部 capability。

## 10. Compose 部署拓扑

`deploy/compose.production.yml` 包含：

- `database`：PostgreSQL 17 + pgvector 0.8.6，只加入内部网络，不映射 5432 到宿主机。
- `migrate`：一次性运行 Alembic；成功后才允许应用启动。
- `backend`：FastAPI 接口，只有一个实例。
- `worker`：持续轮询数据库任务的独立工作进程。
- `frontend`：Nginx 静态文件和反向代理，只暴露 8080。

PostgreSQL 和对象文件分别使用命名持久卷。删除或重建应用容器不会自动删除数据卷，但这不等于已经
备份；错误命令、磁盘损坏和服务器丢失仍可能破坏卷。

## 11. 文件型密钥

`deploy/production.env.example` 只保存非敏感配置。真实密码和令牌分别存放在 `deploy/secrets`，通过
Compose secrets 以只读文件挂载到容器。数据库管理员密码只进入 PostgreSQL 容器，初始化脚本用它启用
pgvector 并创建非超级用户、不能创建数据库和角色的 `rag_app`；后端只读取 `rag_app` 的独立密码。
后端入口脚本读取应用密钥后再启动应用。

与把密钥写入镜像或 Compose YAML 相比，这减少了 Git 泄露和镜像层残留。它仍是单机过渡方案；正式
企业环境应使用受管密钥服务、访问审计和定期轮换。

## 12. 独立迁移与兼容策略

数据库迁移只执行一次，不让每个后端副本同时运行 Alembic。`migrate` 失败时依赖它的服务不会启动。

企业数据库改动推荐：

1. **扩展**：先添加允许为空的新列或新表，旧应用仍能工作。
2. **迁移**：回填数据并让新应用开始读写新结构。
3. **收缩**：确认旧版本不再使用后，另一次发布再删除旧结构。

这叫做“扩展与收缩迁移”，用于减少发布与数据库结构紧密耦合。

## 13. 备份与恢复

`scripts/backup-postgresql.ps1` 使用 `pg_dump` 自定义格式生成归档和 SHA-256 校验。
`scripts/restore-postgresql-rehearsal.ps1` 只允许恢复到 `_restore` 结尾的新数据库，拒绝覆盖现有库。

本步没有实际创建备份，因为这会读取并复制你的当前业务数据库，应该在你明确选择备份时间和存储位置
后执行。详细步骤见 [备份与恢复手册](operations/backup-and-restore.md)。

## 14. 本机验证

无需 Docker：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-deployment.ps1
```

本次已经验证：

- 18 个部署专项测试全部通过；
- GitHub Actions、Dependabot 和 Compose 共 5 份 YAML 通过 Prettier 解析；
- 生产配置会拒绝开启交互文档；
- 启用指标时生产配置会拒绝缺少监控令牌；
- 持续文档工作进程的批量边界通过测试；
- 数据库未暴露宿主机端口；
- Nginx 保留回答事件流并屏蔽公共 `/metrics`。

当前完整验收结果为后端 119 个测试全部通过、分支覆盖率 82.56%；前端最近一次基线为 14 个单元测试和 2 个浏览器流程
全部通过，前端语句覆盖率 94.33%、分支覆盖率 80%。免费的 135 题确定性完整 RAG 门禁通过，Top 5 命中率、
平均倒数排名和归一化折损累计增益均为 1.000。Docker 镜像只能在安装 Docker 后或推送到 GitHub 后实际
构建，所以当前不能声称镜像运行测试已经在本机通过。

## 15. 分支保护建议

最后建立 GitHub 仓库后，在 `main` 分支设置：

- 必须通过质量门禁才能合并；
- 必须解决审查意见；
- 禁止强制推送；
- 禁止直接删除主分支；
- 团队环境要求至少一名其他成员批准；
- 生产 environment 要求指定批准者，并限制允许部署的版本标签。

当前仓库主要由单一维护者开发，暂时使用自查清单；引入协作者后应启用至少一名其他成员批准。

## 16. 当前限制

1. GitHub Actions 已有真实运行记录；首次运行发现依赖源遗漏，修复后的最终结论以 Actions 页面为准。
2. 本机没有 Docker，所以镜像与 Compose 只完成静态验证。
3. 没有真实服务器，未完成公网 HTTPS、生产监控和真实回滚演练。
4. 单后端实例仍使用进程内限流和缓存。
5. 工作进程使用 PostgreSQL 轮询，没有 Redis 与 Celery。
6. 对象文件使用本地卷，没有实现对象存储跨机容灾。
7. 备份和恢复脚本已经提供，但本步没有擅自复制或恢复你的数据库。

这些限制会保留在项目文档中，避免把“生产式设计”表述成“已经生产运行”。

### 首次远程运行复盘

首次主分支流水线中，前端任务完整通过，后端测试和确定性 RAG 任务在导入 DOCX 解析器时失败。根因不是
业务逻辑或数据库，而是 `pyproject.toml` 已声明 `python-docx` 与 `pypdf`，用于生成锁文件的
`requirements.in` 却遗漏了它们。本机虚拟环境曾经安装过完整项目，所以缺失被长期环境掩盖；干净的
Linux 执行器只按锁文件安装，立即暴露 `ModuleNotFoundError`。

修复包括：补齐唯一依赖输入、重新生成运行与开发锁文件，并新增契约测试，要求项目声明、依赖输入和锁
文件保持一致。这说明持续集成的价值不只是重复本地命令，还包括用干净环境发现环境漂移。

第二次运行中，文档摄取与 RAG 任务已恢复，随后又发现两个测试错误继承了流水线的安全环境变量：接口
文档按远程配置关闭，指标端点按远程配置要求令牌，而测试仍假设本地默认值。共享测试夹具因此显式固定
测试所需配置，生产安全行为继续由独立配置测试覆盖。这说明可靠测试必须隔离外部环境，不能依赖开发机的
`.env` 恰好是什么值。

## 17. 官方资料

- [GitHub Actions：理解工作流、任务和步骤](https://docs.github.com/en/actions/get-started/understand-github-actions)
- [GitHub Actions：PostgreSQL 服务容器](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)
- [GitHub Actions：依赖缓存](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GitHub Actions：部署环境和保护规则](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [GitHub Actions：发布容器镜像](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [Docker：Dockerfile 参考](https://docs.docker.com/reference/dockerfile)
- [Docker：Compose 服务与健康检查](https://docs.docker.com/reference/compose-file/services/)
- [Docker：Compose secrets](https://docs.docker.com/reference/compose-file/secrets/)
- [pgvector 官方 Docker 镜像版本](https://github.com/pgvector/pgvector)
- [PostgreSQL 17：备份与恢复](https://www.postgresql.org/docs/17/backup-dump.html)

## 18. 本步知识点总结

1. 持续集成把团队约定变成每次变更都执行的自动证据。
2. 持续交付产生可部署制品，持续部署才是自动上线；高风险系统不应混淆两者。
3. 测试和发布必须调用同一套质量门禁，避免流程漂移。
4. RAG 的常规流水线应使用确定性评测，真实外部模型实验需要费用与数据授权。
5. 应该构建一次并推广同一个镜像，不能在每个环境重新临时构建。
6. 数据库迁移必须独立执行，并优先采用向后兼容的扩展与收缩方式。
7. 镜像非根运行、只读文件系统、内部网络和文件型密钥属于纵深防御。
8. 标签便于阅读，摘要才能精确指向不可变镜像内容。
9. 备份只有经过恢复演练才具有可信恢复价值。
10. 没有真实流水线、服务器和演练证据时，必须明确说“配置已完成”，不能说“已经生产上线”。
