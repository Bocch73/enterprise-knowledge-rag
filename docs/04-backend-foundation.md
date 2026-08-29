# 第 4 步：搭建可运行、可测试的后端最小骨架

## 1. 本步目标

这一阶段先不写用户、文档或检索业务，也不连接数据库。目标是建立以后所有业务模块都会依赖的“地基”：

1. 应用能够真实启动，并自动生成接口说明。
2. 配置不写死在代码里，并且启动前会校验。
3. 每个请求都有请求编号，响应与日志可以对应起来。
4. 所有错误使用同一种响应结构，未知异常不会泄露内部信息。
5. 区分“进程活着”和“服务可以接流量”。
6. 测试、代码规范、格式和类型检查可以一条命令重复执行。

这符合企业开发的一个重要原则：先建立可维护、可观测、可验证的最小服务，再在上面增加业务功能。

## 2. 先认识目录

```text
backend/
├─ app/
│  ├─ api/v1/           第 1 版网络接口和路由
│  ├─ core/             配置、日志、错误和中间件等公共能力
│  ├─ schemas/          请求与响应的数据结构
│  └─ main.py           创建应用和启动入口
├─ tests/               自动化测试
├─ .env.example         可公开的配置示例，不放真实密码
├─ pyproject.toml       项目元数据和工具规则
├─ requirements.in      生产环境直接依赖
├─ requirements.lock    生产环境完整锁定依赖
├─ requirements-dev.in  开发和测试直接依赖
└─ requirements-dev.lock 开发和测试完整锁定依赖
```

`api/v1` 中的 `v1` 表示接口第 1 版。以后出现不兼容修改时可以增加 `v2`，给调用方迁移时间。

## 3. 安装方式为什么分成输入文件和锁文件

- `requirements.in` 只写团队主动选择的直接依赖，便于阅读和评审。
- `requirements.lock` 由工具解析生成，还固定全部间接依赖版本，便于重复安装。
- 开发锁文件比生产锁文件多出测试、格式和类型检查工具，避免把开发工具部署到生产环境。

当前虚拟环境已经安装完成。以后重新安装开发依赖时，在 `backend` 目录运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
```

当 `.in` 文件发生变化时，重新生成锁文件：

```powershell
.\.venv\Scripts\python.exe -m piptools compile --strip-extras --output-file requirements.lock requirements.in
.\.venv\Scripts\python.exe -m piptools compile --strip-extras --output-file requirements-dev.lock requirements-dev.in
```

注意：不要直接手改锁文件，因为它是解析结果；应修改输入文件后重新生成。

## 4. 应用工厂与启动入口

[`backend/app/main.py`](../backend/app/main.py) 中的 `create_app` 是应用工厂，即“负责创建应用的函数”。它集中完成配置读取、日志初始化、中间件、异常处理器和路由注册。

这样设计的价值是：

- 生产运行和测试使用同一套组装逻辑。
- 测试可以传入专用配置，创建彼此隔离的应用实例。
- 将来增加数据库连接、生命周期管理时有唯一入口。

模块最后的 `app = create_app()` 是 Uvicorn 默认加载的实例。`app.main:app` 的冒号左边是 Python 模块，右边是模块中的变量。

## 5. 配置体系

[`backend/app/core/config.py`](../backend/app/core/config.py) 使用数据模型读取以 `RAG_` 开头的环境变量，也会在本地读取 `.env` 文件。

例如：

```text
RAG_ENVIRONMENT=local
RAG_LOG_LEVEL=INFO
RAG_DOCS_ENABLED=true
```

配置字段有明确类型和范围。例如就绪检查超时时间必须大于 0 且不超过 30 秒；生产环境禁止打开调试模式。如果配置错误，应用会在启动时直接失败，比运行到一半才报错更安全。

`.env.example` 只告诉开发者需要哪些配置。以后真正的密码放在 `.env`，而 `.gitignore` 会阻止它进入版本库。

## 6. 请求编号、中间件和结构化日志

[`backend/app/core/middleware.py`](../backend/app/core/middleware.py) 是每个网络请求都会经过的公共层。

处理顺序如下：

```text
请求进入
  → 读取并校验 X-Request-ID；没有则生成
  → 保存到当前异步任务的上下文变量
  → 调用实际接口
  → 响应加入请求编号和安全响应头
  → 记录方法、路径、状态码和耗时
  → 清理当前请求的上下文
```

请求编号不是用户身份，也不是安全令牌。它只是排障线索。服务只接受长度和字符符合规则的外部编号，避免恶意超长值或控制字符污染日志。

[`backend/app/core/logging.py`](../backend/app/core/logging.py) 把日志输出为 JSON。相较于自由文本，JSON 字段可以被日志平台稳定检索。例如客服提供 `request_id` 后，工程师可以找到该请求的访问日志和错误日志。

## 7. 统一错误响应

所有公开错误都使用类似结构：

```json
{
  "error": {
    "code": "request_validation_error",
    "message": "Request validation failed",
    "request_id": "...",
    "details": []
  }
}
```

- `code` 是稳定的机器可读错误码，前端不应依赖容易变化的文字。
- `message` 是给人看的概述。
- `request_id` 用于关联日志。
- `details` 是可选的字段级信息。

已知业务错误用 `AppError` 表达；参数错误和不存在的路径也会被转换成同一结构；未知异常对外只返回安全的通用信息，完整异常只进入服务端日志。

## 8. 为什么有两个健康检查

### 存活检查

`GET /api/v1/health/live` 只判断应用进程能否响应。它不检查数据库，否则数据库短暂故障可能导致应用被反复重启，放大故障。

### 就绪检查

`GET /api/v1/health/ready` 判断服务能否接收业务流量。现在只有应用自身检查；第 5 步接入数据库后会增加数据库检查。必要依赖不可用时返回 503，表示服务暂时不可用，入口层应暂停给该实例发送新请求。

两类检查解决不同问题：存活失败倾向于重启实例，就绪失败倾向于暂时摘除流量。

## 9. 启动并亲手验证

在 PowerShell 中运行：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.server --reload
```

`--reload` 表示开发期间源代码变化后自动重启；生产环境不应使用它。

浏览器访问：

- <http://127.0.0.1:8000/docs>：可交互的接口说明页面。
- <http://127.0.0.1:8000/api/v1/health/live>：存活检查。
- <http://127.0.0.1:8000/api/v1/health/ready>：就绪检查。

停止服务时回到终端按 `Ctrl+C`。

## 10. 自动化质量门禁

在项目根目录运行：

```powershell
.\scripts\verify-backend.ps1
```

它依次执行：

1. Pytest 自动化测试以及分支覆盖率统计，最低门槛为 80%。
2. Ruff 代码规范检查，发现未使用导入、潜在缺陷和部分安全问题。
3. Ruff 格式检查，保证团队排版一致。
4. Mypy 严格静态类型检查，检查参数和返回值类型。

覆盖率表示测试运行到了多少代码，不等于测试质量，也不能证明没有缺陷。企业项目应同时关注关键业务场景、边界条件和失败路径。

## 11. 本次真实验证结果

- Python：3.11.6。
- 自动化测试：18 个全部通过。
- 分支覆盖率：96.79%，高于 80% 门槛。
- Ruff 代码规范与格式：通过。
- Mypy 严格类型检查：21 个源文件零错误。
- 真实启动：存活检查、就绪检查、OpenAPI 文件均返回 200。
- 日志验证：调用方传入的 `manual-check-001` 同时出现在响应头和结构化日志。

测试输出有一条来自 FastAPI/Starlette 测试客户端的第三方弃用警告。目前功能正常、测试通过；后续升级依赖时应重新验证并消除该警告，不能用全局忽略掩盖未知警告。

## 12. 官方学习资料

- [FastAPI：大型应用的多文件组织](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [FastAPI：测试](https://fastapi.tiangolo.com/tutorial/testing/)
- [Pydantic Settings：配置管理](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Python 日志指南：上下文变量](https://docs.python.org/3/howto/logging-cookbook.html#use-of-contextvars)
- [Pytest：用法](https://docs.pytest.org/en/stable/how-to/usage.html)
- [Ruff：配置](https://docs.astral.sh/ruff/configuration/)
- [Mypy：入门](https://mypy.readthedocs.io/en/stable/getting_started.html)
- [pip-tools：项目页面](https://pypi.org/project/pip-tools/)

## 13. 本步完成标准

- [x] 应用能在本机启动。
- [x] 存活与就绪接口可真实访问。
- [x] 环境配置有类型和安全校验。
- [x] 错误响应统一且未知异常不泄露内部信息。
- [x] 每个请求有可追踪编号和 JSON 日志。
- [x] 自动化测试、覆盖率、格式、规范和类型检查通过。
- [x] 依赖输入文件和完整锁文件已生成。
- [x] 教程、知识总结和术语已补齐。

下一步将建立 PostgreSQL 数据模型、数据库迁移以及身份和角色权限。那一步才需要真正准备数据库；本步骤不需要 Docker。
