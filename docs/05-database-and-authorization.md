# 第 5 步：PostgreSQL、数据库迁移、身份认证与权限授权

## 1. 本步目标

第 4 步只有可运行的服务外壳。本步骤让系统第一次拥有持久数据和安全边界：

1. 后端连接 PostgreSQL 17.11，而不是把数据只放在内存中。
2. 数据库结构由版本化迁移创建，能够检查漂移、升级和回退。
3. 用户可以注册、登录并查询自己的身份。
4. 密码只保存 Argon2 哈希，任何响应和日志都不返回明文或哈希。
5. 登录成功后签发有过期时间和签名的访问令牌。
6. 同时实现应用全局角色和知识库资源角色。
7. 未授权用户无法通过资源编号发现其他人的知识库。

## 2. 本机数据库实际状态

| 项目 | 当前值 |
|---|---|
| PostgreSQL | 17.11，Windows 64 位 |
| 服务 | `postgresql-x64-17`，运行中、自动启动 |
| 正式本地数据库 | `rag1` |
| 测试数据库 | `rag1_test` |
| 正式应用账户 | `rag_app`，非超级管理员 |
| 测试应用账户 | `rag_app_test`，非超级管理员 |
| 迁移版本 | `20260826_0001` |

两个应用账户都不能创建数据库、不能创建其他角色、不能复制数据流，也不能绕过行级安全策略。正式库和测试库使用不同账户，测试清理逻辑还会检查数据库名必须以 `_test` 结尾。

数据库超级管理员 `postgres` 只用于首次创建数据库和账户，应用运行时不使用它。当前超级管理员密码过于简单，应在熟悉操作后更换为长且唯一的密码；不要把新密码发到聊天、截图、代码或 Git 中。

## 3. 为什么要分正式库和测试库

自动化测试会反复创建和删除用户、角色关联和知识库。如果测试连接正式库，就可能删除真实数据。因此项目创建独立 `rag1_test`，并在每个测试开始前只清理测试业务数据。

这是企业项目非常重要的安全护栏：测试代码不能仅依赖开发者“记得切换数据库”，而要在代码中验证目标数据库名称。

## 4. 数据库账户与应用角色不是一回事

### PostgreSQL 角色

PostgreSQL 用“角色”同时表达数据库账户和权限主体。`rag_app` 是数据库连接账户，控制能否连接、建表和执行查询。

### 业务应用角色

`admin` 和 `member` 保存在 `application_roles` 表中，用于决定登录用户能否调用某类接口。

两者名字都叫角色，但处于不同层：数据库角色保护数据库服务器，应用角色保护业务功能。

## 5. 数据访问组件

- SQLAlchemy 负责用 Python 模型表达表和关系，并管理事务。
- Psycopg 负责真正与 PostgreSQL 交换网络消息。
- Alembic 负责按版本修改数据库结构。

本项目使用异步数据库会话。请求等待数据库返回结果时，可以让事件循环处理其他请求。Windows 默认事件循环与异步 Psycopg 不兼容，所以项目提供 `app.server` 启动入口，明确选择兼容的选择器事件循环。

不要直接使用普通的 `python -m uvicorn app.main:app` 命令；在本项目 Windows 环境中统一使用：

```powershell
.\.venv\Scripts\python.exe -m app.server --reload
```

## 6. 数据模型

完整关系图见 [第 5 步数据模型](architecture/data-model.md)。

本次创建五组核心表：

1. `users`：用户邮箱、显示名称、密码哈希、启用状态和登录时间。
2. `application_roles`：全局角色，迁移会插入 `admin` 和 `member`。
3. `user_roles`：用户和全局角色的多对多关系。
4. `knowledge_bases`：知识库容器及其所有者。
5. `knowledge_base_memberships`：用户在某个知识库中的资源权限。

## 7. 什么是数据库迁移

迁移是按顺序保存的数据库结构变更。它解决“开发者电脑已经加过字段，但测试服务器还没有”的环境不一致问题。

升级正式本地数据库：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

查看当前版本：

```powershell
.\.venv\Scripts\python.exe -m alembic current
```

检查模型与数据库是否漂移：

```powershell
.\.venv\Scripts\python.exe -m alembic check
```

`head` 表示迁移链的最新版本。迁移虽然支持 `downgrade`，但正式生产环境回退前必须评估数据丢失风险和备份，不能看到命令就直接执行。

## 8. 密码是怎样保护的

注册时的明文密码只在当前请求内存在，随后使用 Argon2 生成带随机盐值的哈希。数据库只保存类似 `$argon2id$...` 的结果。

登录时系统不是“解密密码”，而是让 Argon2 使用相同参数验证候选密码。未知邮箱也执行一次假的哈希验证，减小攻击者通过响应时间判断邮箱是否存在的可能性。

当前密码规则是 12 至 128 个字符。长度是基础防线，不要求用户机械组合固定数量的大小写和符号；真实企业系统还应加入泄露密码库检测、登录限速和多因素认证。

## 9. 访问令牌

登录接口使用 OAuth2 密码表单，其中 `username` 字段填写邮箱。成功后返回 Bearer 类型的 JSON 网络令牌。

令牌包含：

- `sub`：用户编号。
- `iat`：签发时间。
- `exp`：过期时间，当前为 30 分钟。
- `iss`：签发者。
- `aud`：预期接收者。
- `jti`：令牌唯一编号。
- `type`：令牌用途，目前是 `access`。

JSON 网络令牌有签名但没有加密，任何拿到令牌的人都能读取载荷，所以不能在里面放密码等秘密。后端每次仍会查询数据库，确认用户存在且未停用；因此账户停用后，旧令牌会立即失效。

## 10. 两层权限模型

### 全局角色

- `member`：普通登录用户，注册时自动获得。
- `admin`：可以使用全局管理接口。

### 知识库资源角色

- `owner`：创建者，可以管理成员。
- `editor`：为后续上传和编辑文档预留。
- `viewer`：只能读取被授权内容。

普通用户查询知识库时，权限条件直接进入 SQL 查询，而不是先查出全部知识库再由 Python 过滤。无权访问某个知识库时统一返回 404，避免攻击者通过编号探测资源是否存在。

## 11. 首次创建管理员

不要把管理员密码写在命令参数中，因为命令历史可能保存参数。项目提供隐藏密码输入的交互工具：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.cli.create_admin
```

依次输入：

1. 管理员邮箱。
2. 显示名称。
3. 至少 12 个字符的管理员密码。
4. 再次输入密码。

密码输入时屏幕不会显示字符。命令可重复执行：已有用户会被提升为管理员，已经是管理员时不会重复插入角色。

## 12. 亲手体验接口

启动服务：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.server --reload
```

打开 <http://127.0.0.1:8000/docs>，按顺序尝试：

1. `POST /api/v1/auth/register` 注册普通用户。
2. 页面右上角 `Authorize`，用户名填写邮箱，密码填写注册密码。
3. `GET /api/v1/auth/me` 查看当前用户。
4. `POST /api/v1/knowledge-bases` 创建知识库。
5. `GET /api/v1/knowledge-bases` 查看自己有权限的知识库。
6. `PUT /api/v1/knowledge-bases/{id}/members` 由所有者添加成员。

## 13. 自动化验证

项目根目录运行：

```powershell
.\scripts\verify-backend.ps1
```

当前真实结果：

- 32 个测试全部通过。
- 分支覆盖率 84.80%，门槛为 80%。
- 迁移升级、回退、重新升级均在 `rag1_test` 验证成功。
- `alembic check` 没有发现模型与数据库结构漂移。
- Ruff 规范与格式通过。
- Mypy 严格检查 47 个源文件零错误。
- 真实网络演练：就绪 200、注册 201、登录 200、查询当前用户 200、创建知识库 201。

仍存在一条 FastAPI/Starlette 测试客户端的第三方弃用警告，已作为依赖升级技术债记录；它不影响真实网络服务。

## 14. 官方学习资料

- [PostgreSQL 17：数据库角色属性](https://www.postgresql.org/docs/17/role-attributes.html)
- [PostgreSQL 17：创建数据库](https://www.postgresql.org/docs/17/manage-ag-createdb.html)
- [SQLAlchemy 2：异步输入输出](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy 2：Psycopg 方言](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
- [Alembic 教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [FastAPI：OAuth2、密码哈希和 JSON 网络令牌](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)

## 15. 本步完成标准

- [x] 正式库和独立测试库创建完成。
- [x] 后端不使用 PostgreSQL 超级管理员运行。
- [x] 模型、第一版迁移和基础角色完成。
- [x] 迁移升级、回退、漂移检查完成。
- [x] 注册、登录、当前用户和管理员引导完成。
- [x] Argon2 密码哈希和短期签名令牌完成。
- [x] 全局角色和知识库资源权限完成。
- [x] 横向越权和垂直越权测试完成。
- [x] 真实 PostgreSQL 集成测试与网络演练完成。
- [x] 教程、数据图和术语完成。

下一步是第 6 步“文档摄取”：上传文件、文件类型和大小校验、对象存储抽象、文档版本、解析任务状态与失败恢复。pgvector 会在第 7 步再安装。
