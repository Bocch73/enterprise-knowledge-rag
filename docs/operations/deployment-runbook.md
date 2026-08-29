# 部署运行手册

## 1. 适用范围

本手册描述单台 Linux 服务器上的生产式部署流程，用于预发布演练和面试展示。当前还没有已授权的真实
服务器，因此项目只交付配置、检查和操作顺序，不声称已经完成线上部署。

当前方案包含一个前端入口、一个后端接口进程、一个文档工作进程和一个 PostgreSQL 17 数据库。它没有
接入 Redis，所以不能把后端水平扩展到多个实例。

## 2. 部署前置条件

服务器需要：

- 64 位 Linux；
- Docker Engine 和 Docker Compose 2.22 或更高版本；
- 至少 4 个中央处理器核心、8 GB 内存和足够的持久磁盘作为演示起点；
- 只对外开放反向代理端口，PostgreSQL 5432 不能直接暴露；
- 已配置域名和 HTTPS 证书；本项目 Compose 文件只提供内部 HTTP，正式公网入口必须再接入 HTTPS；
- 有独立备份目录或远程备份存储。

容量数字不是承诺。上线前必须按照真实文档量、并发数和模型延迟进行负载测试。

## 3. 文件与密钥准备

复制非敏感配置：

```powershell
Copy-Item .\deploy\production.env.example .\deploy\production.env
```

复制五个密钥模板，但不要把生成后的文件提交到 Git：

```powershell
Copy-Item .\deploy\secrets\postgres_admin_password.example .\deploy\secrets\postgres_admin_password
Copy-Item .\deploy\secrets\database_password.example .\deploy\secrets\database_password
Copy-Item .\deploy\secrets\jwt_secret_key.example .\deploy\secrets\jwt_secret_key
Copy-Item .\deploy\secrets\deepseek_api_key.example .\deploy\secrets\deepseek_api_key
Copy-Item .\deploy\secrets\metrics_bearer_token.example .\deploy\secrets\metrics_bearer_token
```

数据库密码、JSON 网络令牌密钥和监控令牌建议使用密码学安全的随机十六进制值。当前入口脚本把数据库
密码放入连接地址，因此数据库密码必须使用网址安全字符，十六进制值最简单。

```powershell
[Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()
```

数据库管理员密码只供 PostgreSQL 容器初始化使用；后端只取得受限业务账号的独立密码。DeepSeek 密钥
从已忽略的本地文件复制到 `deploy/secrets/deepseek_api_key`。五个真实密钥文件都被
`deploy/.gitignore` 排除。正式企业环境应使用云密钥管理服务或编排平台密钥，不应长期把密钥作为
普通服务器文件保存。

## 4. 部署前静态检查

没有 Docker 的开发电脑可以运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-deployment.ps1
```

它验证生产安全配置、持续工作进程、镜像约束、Compose 安全边界和 YAML 语法，不启动任何容器。

安装 Docker 的 Linux 或 Windows 环境还应执行：

```powershell
docker compose --env-file .\deploy\production.env `
  -f .\deploy\compose.production.yml config
```

`docker compose config` 会解析变量、合并锚点并验证 Compose 结构，但仍不启动服务。

## 5. 构建与启动顺序

从项目根目录执行：

```powershell
docker compose --env-file .\deploy\production.env `
  -f .\deploy\compose.production.yml build --pull

docker compose --env-file .\deploy\production.env `
  -f .\deploy\compose.production.yml up -d
```

Compose 会按以下顺序协调：

1. 启动 PostgreSQL，以管理员身份启用 pgvector 并创建非超级用户 `rag_app`，再等待 `pg_isready` 健康检查通过。
2. 运行一次性 `migrate` 服务，把数据库升级到 Alembic 最新版本。
3. 迁移成功后启动后端和文档工作进程。
4. 后端健康后启动前端 Nginx。

迁移失败时后端不会启动。不要通过删除依赖条件来绕过失败，应先查看迁移日志：

```powershell
docker compose --env-file .\deploy\production.env `
  -f .\deploy\compose.production.yml logs migrate
```

## 6. 部署后验证

查看容器状态：

```powershell
docker compose --env-file .\deploy\production.env `
  -f .\deploy\compose.production.yml ps
```

默认入口：

- 前端：`http://服务器地址:8080`；
- 前端健康检查：`GET /healthz`；
- 后端存活检查：`GET /api/v1/health/live`；
- 后端就绪检查：`GET /api/v1/health/ready`。

必须继续执行人工冒烟检查：

1. 注册或使用演示账号登录。
2. 创建知识库。
3. 上传一份虚构 Markdown 文档。
4. 确认工作进程把任务变为完成。
5. 执行检索。
6. 提问并检查引用能定位原文。
7. 使用管理员账号查询审计事件和任务队列。

`/metrics` 被公共 Nginx 明确返回 404。未来 Prometheus 应加入内部 `backend` 网络并携带独立监控令牌，
不能为了采集方便把指标直接暴露到互联网。

## 7. 日志与运行观察

查看最近日志：

```powershell
docker compose --env-file .\deploy\production.env `
  -f .\deploy\compose.production.yml logs --tail 200 backend worker frontend database
```

Compose 把每个容器的 JSON 日志文件限制为 10 MB，并最多保留 5 个轮转文件，避免日志无限占满磁盘。
这只是单机保护；正式环境还应把结构化日志发送到集中日志平台，并对错误率、任务积压和第 95 百分位
延迟配置告警。

## 8. 发布新版本

企业流程不在服务器直接修改源码：

1. 拉取请求通过持续集成。
2. 人工审查变更和数据库迁移。
3. 主分支形成版本标签，例如 `v0.2.0`。
4. 发布工作流重新执行全部门禁。
5. 工作流把前后端镜像推送到 GitHub Container Registry。
6. 预发布环境使用确定版本或镜像摘要验证。
7. 获得生产批准后更新 `RAG_IMAGE_TAG` 并部署。

不要使用 `latest`。版本标签方便理解，镜像摘要则是内容不可变的精确标识，关键生产部署应记录摘要。

## 9. 回滚

应用错误且数据库迁移向后兼容时：

1. 停止继续发布。
2. 保存错误日志、请求编号和当前镜像摘要。
3. 把 `RAG_IMAGE_TAG` 改回上一个已验证版本。
4. 重新启动后端、工作进程和前端。
5. 重做健康检查与关键业务冒烟。

不要默认执行 `alembic downgrade`。数据库降级可能丢列、丢数据或破坏新版本已经写入的记录。企业常用
“先扩展、后迁移、再收缩”的兼容迁移方式，使上一版和下一版能在一段时间内共同使用数据库。

如果迁移已经造成不可兼容数据损坏，应启动事故流程，从部署前备份恢复到新数据库，再由负责人决定
切换。具体见 [备份与恢复手册](backup-and-restore.md)。

## 10. 停止条件

出现以下任一情况应停止发布：

- 质量门禁未全部通过；
- 数据库备份失败或恢复演练超过恢复时间目标；
- 迁移脚本没有人工审查；
- 环境密钥缺失、泄露或仍是模板值；
- 就绪检查失败；
- 错误率、延迟、数据库连接或任务积压明显异常；
- 没有明确回滚版本和负责人。

## 11. 当前边界

- 没有真实服务器，因此没有实际上线证据。
- 没有 HTTPS 终止层，公网部署前必须补充。
- 没有 Redis 与 Celery，当前工作进程使用 PostgreSQL 轮询。
- 只有一个后端实例，进程内限流和缓存不会出现跨实例不一致。
- Compose 文件适合单机预发布或演示，不等同于 Kubernetes 高可用集群。
- 当前对象文件使用本地持久卷，生产应评估具备版本和备份能力的对象存储。
