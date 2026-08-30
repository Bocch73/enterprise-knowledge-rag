# 本地多进程运行手册

## 1. 目标

本地开发需要同时运行三个互相独立的程序：

| 程序 | 职责 | 默认地址或通信方式 |
|---|---|---|
| 后端接口 | 接收页面请求，执行身份、权限、检索和问答逻辑 | `http://127.0.0.1:8000` |
| 文档处理进程 | 从 PostgreSQL 领取任务，执行解析、分块和索引 | 通过 PostgreSQL 任务表通信，不开放端口 |
| 前端页面 | 提供浏览器操作界面，并把 `/api` 请求转发到后端 | `http://127.0.0.1:5173` |

**进程**是操作系统中正在运行的程序实例。三个独立进程表示它们拥有不同的进程编号，其中一个停止时，
另外两个不一定随之停止。这种边界便于查看日志、隔离故障，并为以后分别扩容打基础。

## 2. 首次使用前的条件

统一入口不会替代安装和数据库迁移。第一次使用前确认：

1. PostgreSQL 17 正在运行，且已经安装 pgvector 0.8.6。
2. `backend/.env` 已填写本地数据库连接和应用配置。
3. `backend/.venv` 已安装 `requirements-dev.lock` 中的依赖。
4. 已执行 `python -m alembic upgrade head`，让数据库结构升级到当前版本。
5. `frontend/node_modules` 已通过 `npm ci` 安装。

**数据库迁移**是用有版本记录的脚本逐步更新数据库结构。它让不同开发者和不同环境得到一致的数据表，
而不是手工修改数据库后无法追踪差异。

## 3. 统一启动

在项目根目录运行：

```powershell
cd "E:\codex项目\rag1"
powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Start
```

脚本依次完成以下工作：

1. 检查 Python、Node.js、后端配置和前端依赖是否存在。
2. 检查 8000 与 5173 端口是否空闲。
3. 分别创建后端接口、文档处理进程和前端页面进程。
4. 保存三个进程编号，但不保存数据库密码或 DeepSeek 密钥。
5. 请求后端就绪检查和前端首页，确认系统真的可以响应。

**端口**是同一台电脑上区分不同网络服务的数字。这里 8000 属于后端，5173 属于前端。如果端口已被其他
程序占用，脚本会停止启动并给出提示，避免页面连接到错误的旧进程。

**就绪检查**是服务主动回答“我依赖的组件是否可用”。后端进程存在并不代表数据库可连接，所以统一入口
检查 `/api/v1/health/ready`，而不只检查 Python 是否还在运行。

## 4. 查看状态与日志

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Status
```

输出中的“进程编号”也称为 Process Identifier，是操作系统分配给每个运行实例的数字，常写作 PID。

日志位于 `.dev-runtime/logs`，每次启动使用新的时间戳文件，文件名分别包含：

- `backend.out.log` 和 `backend.error.log`：后端正常输出与错误输出。
- `worker.out.log` 和 `worker.error.log`：文档处理记录与异常。
- `frontend.out.log` 和 `frontend.error.log`：前端开发服务器输出与异常。

**标准输出**通常记录正常运行信息，**标准错误**通常记录警告和异常。把二者分开保存，可以更快定位问题。
`.dev-runtime` 已写入 `.gitignore`，因此本地运行记录不会进入版本库。

## 5. 统一停止或重启

统一停止：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Stop
```

脚本只停止状态文件中记录且身份匹配的进程，并一并清理它们创建的子进程。文档处理如果正在执行数据库事务，
PostgreSQL 会回滚未提交事务；项目已有超时任务恢复机制，但开发时仍建议等待当前上传处理完成后再停止。

修改配置后需要完整重启时：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Restart
```

后端默认开启代码自动重载。若要排查自动重载产生的子进程问题，可以禁用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-services.ps1 -Action Start -NoReload
```

## 6. 常见问题

### 提示端口已被占用

先运行 `-Action Status`。如果显示三个服务正在运行，不要重复启动；使用现有页面，或先执行 `-Action Stop`。
如果状态显示没有服务，说明端口由其他程序占用，需要先确认并关闭那个程序。

### 后端未通过启动检查

优先查看最新的 `backend.error.log`，然后确认 PostgreSQL 服务、`backend/.env` 中的数据库地址，以及数据库迁移。
启动失败时脚本会停止本轮已经创建的其他进程，避免留下半套系统。

### 文档上传后一直等待

先用 `-Action Status` 确认文档处理进程仍在运行，再查看最新的 `worker.error.log`。工作进程不开放网页端口，
因此必须通过进程状态、任务接口和日志共同判断。

## 7. 本步知识小结

1. 统一入口不等于合并进程；它只是集中管理三个独立运行单元。
2. 进程编号用于精确识别和停止本轮启动的程序。
3. 端口检查可避免连接到旧服务或错误服务。
4. 就绪检查比“进程还活着”更能证明系统可用。
5. 分离日志能把前端、接口与后台任务的故障快速归类。

相关文档：

- [开发环境](../02-development-environment.md)
- [文档摄取](../06-document-ingestion.md)
- [前端工作台](../10-frontend-workbench.md)
- [系统架构](../architecture/system-architecture.md)
- [生产部署运行手册](deployment-runbook.md)
