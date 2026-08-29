# 第 2 步总结：开发环境与仓库规范

## 已完成

- 验证 Python 3.11.6，并创建 `backend/.venv` 项目虚拟环境。
- 配置 Visual Studio Code 默认 Python 解释器和推荐扩展。
- 固定 Python 版本，并下载、校验项目专用 Node.js 24.19.0 长期支持版。
- 统一编码、缩进和换行规则。
- 建立分支、提交、拉取请求和合并规范。
- 建立功能需求、缺陷报告和拉取请求模板。
- 验证本地密钥文件与虚拟环境不会进入版本库。
- 建立可重复执行的开发环境检查脚本。

## 主动延期的事项

- Git 提交和远程上传延期到项目形成完整交付版本后统一处理。
- Docker Desktop 延期到进入数据库和缓存集成之前安装。

这些是用户明确选择的阶段安排，不是环境检查遗漏。系统 Node.js 20 没有被覆盖；本项目已通过 Visual Studio Code 设置隔离使用受支持版本。

延迟 Git 提交不会阻止开发，但会失去按步骤保存和恢复历史的能力；真实企业团队通常仍会小步提交。延迟 Docker 不影响需求、架构和不依赖外部基础设施的代码，但在数据库集成前必须解决。

## 必须掌握的知识点

1. 虚拟环境隔离每个 Python 项目的第三方依赖。
2. `.gitignore` 只规定哪些未跟踪文件不应进入版本库，不能用来隐藏已经提交的密钥。
3. 工作区、暂存区和版本库是 Git 的三个基本区域。
4. 分支让开发者在不影响稳定主线的情况下完成和审查功能。
5. 拉取请求是一次正式的变更审查，不只是点击合并按钮。
6. 统一提交格式能让历史更容易阅读，并支持自动生成发布记录。
7. 已停止维护的运行时没有安全更新，不适合新的企业项目。

## 相关资料

- [Visual Studio Code 选择 Python 环境](https://code.visualstudio.com/docs/python/environments)
- [Python 官方版本状态](https://devguide.python.org/versions/)
- [Git 首次配置官方指南](https://git-scm.com/book/en/v2/Getting-Started-First-Time-Git-Setup)
- [GitHub Flow 官方指南](https://docs.github.com/en/get-started/using-github/github-flow)
- [Conventional Commits 规范](https://www.conventionalcommits.org/en/v1.0.0/)
- [Node.js 官方版本状态](https://nodejs.org/en/about/previous-releases)
- [Docker Desktop Windows 安装文档](https://docs.docker.com/desktop/setup/install/windows-install/)
