# 开发环境与仓库规范

## 1. 为什么要统一环境

同一份代码在不同电脑上使用不同运行环境，可能出现“我的电脑能运行，你的电脑却失败”。因此企业项目会明确运行时版本、隔离依赖，并把编辑器和换行规则放进版本库。

**运行时**是执行程序所需要的软件环境，例如 Python 负责执行后端 Python 代码，Node.js 负责执行前端构建工具。

## 2. 当前确认结果

| 项目 | 当前状态 | 项目决定 |
|---|---|---|
| Python | 3.11.6，已创建 `backend/.venv` | 后端第一版使用 Python 3.11 |
| pip | 23.2.1 | 只通过虚拟环境安装依赖，后续锁定依赖版本 |
| Visual Studio Code | 1.128.0 | 作为主要编辑器 |
| Git | 2.53.0 | 使用分支、提交和拉取请求流程 |
| Node.js | 系统版本为 20.17.0；项目便携版为 24.19.0 | Visual Studio Code 项目终端优先使用 24.19.0 长期支持版 |
| npm | 系统版本为 10.8.2；项目便携版为 11.17.0 | 前端依赖使用项目便携版 |
| WSL | 2.5.9 | 满足 Docker Desktop 使用 WSL 2 后端的版本要求 |
| Docker Desktop | 尚未发现 | 安装后才能运行 PostgreSQL 和 Redis 容器 |

**长期支持版**（Long-Term Support）是在较长周期内持续接收稳定性和安全更新的版本，常简称 LTS。企业生产环境通常避免使用已经停止维护的版本。

随时可以运行环境检查脚本：

```powershell
.\scripts\verify-dev-environment.ps1
```

在进入需要数据库容器的步骤前，使用 `-RequireDocker` 参数把缺少 Docker 从警告提升为失败：

```powershell
.\scripts\verify-dev-environment.ps1 -RequireDocker
```

## 3. 在 Visual Studio Code 中打开项目

```powershell
code "E:\codex项目\rag1"
```

打开后：

1. 安装编辑器提示的推荐扩展。
2. 按 `Ctrl+Shift+P` 打开命令面板。
3. 输入并选择 `Python: Select Interpreter`。
4. 确认解释器为 `backend\.venv\Scripts\python.exe`。
5. 新建终端。提示符前出现 `(.venv)` 代表虚拟环境已激活。
6. 执行 `node --version`，应显示 `v24.19.0`；如果终端早于本项目设置创建，请关闭后新建终端。

项目已在 `.vscode/settings.json` 中设置默认解释器。`.vscode/extensions.json` 只推荐扩展，不会未经用户同意自动安装。

**解释器**是读取并执行 Python 代码的程序。选择项目虚拟环境中的解释器，才能使用本项目安装的依赖。

## 4. 不依赖编辑器时激活虚拟环境

```powershell
cd "E:\codex项目\rag1"
.\backend\.venv\Scripts\Activate.ps1
python --version
python -m pip --version
```

如果 PowerShell 阻止激活脚本，不要随意永久放宽整台电脑的安全策略。可以直接运行：

```powershell
.\backend\.venv\Scripts\python.exe --version
```

## 5. 版本文件

- `.python-version` 记录本项目验证过的 Python 版本。
- `.nvmrc` 记录前端目标 Node.js 主版本。
- `.editorconfig` 统一缩进、编码和换行。
- `.gitattributes` 统一版本库中的文本换行，并标记二进制文件。
- `.gitignore` 排除密钥、虚拟环境、依赖目录和运行数据。

## 6. Git 的三个基本区域

1. **工作区**：你正在编辑的文件。
2. **暂存区**：已经挑选、准备放入下一次提交的改动。
3. **版本库**：已经正式提交并形成历史记录的快照。

一次典型流程是：修改文件 → 检查差异 → 放入暂存区 → 创建提交。

## 7. Git 身份为什么不能随便填写

每个 Git 提交都会永久记录作者姓名和邮箱。目前电脑尚未配置这两项，因此本项目不使用虚假信息创建提交。请使用你希望展示在 GitHub 上的姓名和经过验证的邮箱，或者 GitHub 提供的隐私邮箱。

确认后可配置为仅对本项目生效：

```powershell
git config user.name "你的展示姓名"
git config user.email "你的 GitHub 邮箱或隐私邮箱"
```

不加 `--global` 表示只修改当前项目，不影响电脑上的其他版本库。

## 8. 第一次提交将在身份确认后执行

当前决定：学习期间暂不创建 Git 提交，也不上传远程仓库，等项目形成完整交付版本后统一处理。项目仍保留分支、提交和拉取请求规范，最终交付时使用。

需要区分两个动作：`git commit` 只在本地保存历史快照，`git push` 才会把已有提交发送到 GitHub。延迟本地提交不会阻止代码运行，但会减少逐步恢复和查看开发历史的能力；这是当前学习安排的明确取舍。

```powershell
git add .
git status
git commit -m "docs: initialize enterprise RAG project"
```

`git add` 是把改动放进暂存区，不是上传网络；`git commit` 是在本地版本库创建不可变的历史快照，也不是上传到 GitHub。

## 9. Docker Desktop 安装前说明

本项目以后使用容器启动 PostgreSQL 数据库和 Redis 缓存。当前 WSL 2 版本满足 Docker 文档的最低版本要求，但 Docker Desktop 尚未安装。安装属于电脑级变更，并包含许可条款，因此必须由电脑使用者确认后进行。

当前决定：暂不安装 Docker。第 3 步的需求与架构设计以及第 4 步的后端基础骨架可以继续；进入 PostgreSQL、Redis、异步任务或完整集成测试之前必须重新检查并安装。开发期间不把缺少 Docker 误报为系统已经具备部署能力。

本轮曾尝试启动官方每用户安装程序，但图形安装程序没有进入用户桌面会话，因此已经停止，并删除了 366,884,918 字节的临时安装包。项目不会把“下载过安装包”误报为“Docker 已可用”。

Docker Desktop 安装完成后的验证命令：

```powershell
docker --version
docker compose version
docker run --rm hello-world
```

## 10. Node.js 项目便携版

电脑的系统 Node.js 20 已停止维护。为了不覆盖其他项目，本项目从 Node.js 官方下载了 24.19.0 长期支持便携版，保存在被 Git 忽略的 `.tools/node-v24.19.0-win-x64` 中。Visual Studio Code 项目终端会把这个目录放在命令搜索路径最前面。

下载时使用官方 `SHASUMS256.txt` 进行 SHA-256 校验。SHA-256 是一种文件指纹算法：只要文件内容发生变化，计算出的值几乎必然不同。本次校验值为：

```text
57f71ab3652e797d84acddc79c81cc9ff1c6ddb2a1974cdb83f00fee9bff4c73
```

验证：

```powershell
node --version
npm --version
```

预期分别为 `v24.19.0` 和 `11.17.0`。`.nvmrc` 也记录了相同 Node.js 版本，持续集成和其他开发者可以据此选择环境。
