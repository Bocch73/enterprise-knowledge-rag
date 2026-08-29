# 第 6 步：企业级文档上传、不可变版本与后台解析

## 1. 本步目标

这一阶段把一个文件安全地变成“已经保存、可以追踪、已经提取文本”的文档版本。暂时不做文本分块、向量表示和相似度检索，它们属于第 7 步。

本步已经实现：

1. 所有者和编辑者可以上传 PDF、DOCX、Markdown 文件。
2. 默认最大文件为 20 MB，同时检查文件名、扩展名、媒体类型、基本结构和大小。
3. 原文件保存为不可覆盖对象，外部响应不暴露物理存储路径。
4. 每次更新创建新的不可变版本，并保存 SHA-256 指纹。
5. 上传接口只创建等待任务，独立工作进程执行解析。
6. 任务包含等待、运行、完成、失败状态，并记录阶段、进度、次数和安全错误信息。
7. 暂时错误采用有限次数和指数退避；永久格式错误不自动重试。
8. 工作进程崩溃后，超时的运行任务可以回收。
9. 编辑者可以分页预览解析后的文本。

## 2. 新名词解释

### 文档摄取

文档摄取是把外部文件转换成系统内部可检索数据的完整流程。本步完成上传、保存和解析；下一步继续完成分块、向量表示和索引。

### 媒体类型

媒体类型是网络传输中声明内容格式的字符串，例如 PDF 使用 `application/pdf`。扩展名和媒体类型都由客户端提供，不能单独相信，所以系统还检查文件结构。

### 对象存储

对象存储用一个唯一键保存文件内容。业务代码依赖 `ObjectStorage` 抽象，本机实现写入 `backend/data/objects`。将来可以换成兼容 Amazon Simple Storage Service 的存储，而不改文档版本规则。

### 不可变版本

不可变表示已经创建的版本不在原位置被改写。上传更新文件时创建版本 2，而不是覆盖版本 1，因此以后回答的引用能够准确指向当时使用的原文。

### SHA-256 文件指纹

SHA-256 会把任意长度的文件计算成固定长度摘要。文件哪怕变化一个字节，摘要通常也会变化。这里用它检测同一文档的重复内容和核对完整性；它不是加密，不能通过摘要还原文件。

### 后台工作进程

后台工作进程是独立于网络接口、专门执行耗时任务的程序。接口只负责接收并登记任务，因此用户不需要让浏览器一直等待解析结束。

### 状态机

状态机规定对象允许出现哪些状态、怎样转换。本项目任务路径是：

```text
等待 queued → 运行 running → 完成 completed
                         └→ 失败 failed
暂时失败 → 延迟后重新等待
```

### 幂等性

幂等性表示同一个任务被重复交付时不会产生两份有效结果。任务系统可能重复投递，所以解析文本以文档版本编号作为唯一主键，完成任务再次执行也不能创建重复成功结果。

### 指数退避

指数退避表示连续失败后逐步增加等待时间。本项目自动重试的延迟从 1 秒开始按 2 的幂增长，避免存储故障时大量任务不停轰击依赖。

### `FOR UPDATE SKIP LOCKED`

`FOR UPDATE` 会锁住选中的数据库行，`SKIP LOCKED` 会跳过已经被其他工作进程锁住的行。多个工作进程因此可以各自领取不同任务，而不是同时解析同一任务。

## 3. 为什么暂时使用数据库任务队列

正式架构仍计划使用 Redis 消息代理和 Linux Celery 工作进程。你当前暂不安装 Docker，而且 Celery 不支持 Windows 原生作为正式工作平台，因此第 6 步先使用 PostgreSQL 任务表和一个有界本地工作命令。

这不是把耗时解析放回网络请求：接口与工作进程仍然分开，任务状态也持久化。以后替换的是“如何通知工作进程”，文档、版本、任务表、权限和状态接口都可以保留。

## 4. 文件安全校验

系统采用多层校验，而不是只看文件名：

| 层次 | 检查内容 | 防御目标 |
|---|---|---|
| 文件名 | 非空、最长 255 字符、禁止路径分隔符和空字符 | 路径穿越 |
| 扩展名 | 只允许 `.pdf`、`.docx`、`.md`、`.markdown` | 非允许格式 |
| 媒体类型 | 必须和扩展名允许集合一致 | 简单伪装 |
| 流式大小 | 边读取边累计，超过 20 MB 立即拒绝 | 内存和磁盘滥用 |
| PDF 结构 | 检查文件头和结束标识，解析时再次验证 | 伪造 PDF |
| DOCX 结构 | 必须是 ZIP 包并包含关键 Office Open XML 文件 | 伪造 DOCX |
| DOCX 展开限制 | 限制展开总大小和压缩比 | 压缩炸弹 |
| Markdown | 必须使用 UTF-8 编码 | 解析歧义 |

用户原始文件名只作为显示元数据。真正的对象键由随机版本编号生成，例如 `sources/ab/ab...cd.pdf`，因此 `../../secret.txt` 不能控制保存位置。

## 5. 数据模型

本次新增四张表，完整关系图见 [数据模型](architecture/data-model.md)：

- `documents`：一个逻辑文档，例如“员工手册”。
- `document_versions`：每次上传的不可变原文件及其指纹。
- `ingestion_jobs`：后台处理状态、次数、锁和错误。
- `parsed_documents`：某个版本提取出的全文及解析器信息。

迁移版本为 `20260826_0002`。任务调度索引按状态、可执行时间和创建时间排序，帮助工作进程快速领取到期任务。

## 6. 当前接口

| 方法与路径 | 权限 | 用途 |
|---|---|---|
| `POST /api/v1/knowledge-bases/{id}/documents` | 所有者、编辑者 | 上传新文档和版本 1 |
| `GET /api/v1/knowledge-bases/{id}/documents` | 知识库成员 | 列出文档 |
| `GET /api/v1/documents/{id}` | 知识库成员 | 查看文档和版本历史 |
| `POST /api/v1/documents/{id}/versions` | 所有者、编辑者 | 追加不可变版本 |
| `GET /api/v1/documents/versions/{id}/preview` | 所有者、编辑者 | 分页预览解析文本 |
| `GET /api/v1/ingestion-jobs/{id}` | 知识库成员 | 查看任务状态 |
| `POST /api/v1/ingestion-jobs/{id}/retry` | 所有者、编辑者 | 对可重试失败执行一次人工重试 |

没有权限的用户查询文档或任务时返回 404，避免通过编号探测资源。查看者可以看到文档元数据和任务状态，但不能上传、查看解析全文或重试。

## 7. 亲手体验完整流程

### 终端一：启动网络接口

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.server --reload
```

保持终端打开，在 Chrome 地址栏输入 <http://127.0.0.1:8000/docs>。这是网址，要粘贴到地址栏，不是 Google 搜索框。

在接口页面依次完成：

1. 调用 `POST /api/v1/auth/register` 注册用户。
2. 点击右上角 `Authorize`，用户名填邮箱，密码填注册密码。
3. 调用 `POST /api/v1/knowledge-bases` 创建知识库，复制返回的知识库 `id`。
4. 展开 `POST /api/v1/knowledge-bases/{knowledge_base_id}/documents`。
5. 把知识库编号粘贴到 `knowledge_base_id`，点击 `Choose File` 选择文件。
6. `title` 可以填写显示标题，然后点击 `Execute`。
7. 保存返回的 `document.id`、`version.id` 和 `ingestion_job.id`。

刚上传时任务是 `queued`，完整含义是“等待”。

### 终端二：运行本地工作进程

重新打开一个 PowerShell 窗口：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.cli.process_ingestion_jobs --max-jobs 10
```

`--max-jobs 10` 表示本次最多处理 10 个等待任务，然后命令退出。当前这是便于 Windows 学习和演示的有界命令，不是需要永久运行的生产守护进程。

回到接口页面：

1. 调用 `GET /api/v1/ingestion-jobs/{job_id}`，成功后状态应为 `completed`。
2. 调用 `GET /api/v1/documents/versions/{version_id}/preview` 查看解析文本。
3. `offset` 是从第几个字符开始，`limit` 是最多返回多少字符，最大为 10,000。

## 8. 失败与恢复策略

### 永久错误

文件损坏、加密 PDF、没有可提取文本、格式不支持等问题不会因为等待而自行恢复。任务直接失败并标记 `retryable=false`，接口拒绝无意义的反复重试。

### 暂时错误

对象存储短暂不可用可能恢复，因此会有限自动重试。达到上限后任务保留原文件、错误代码和错误消息，并允许所有者或编辑者执行一次受控人工重试。

### 工作进程崩溃

工作进程领取任务时写入锁定时间和工作进程编号。如果长时间停留在运行状态，下次工作进程启动会识别为陈旧任务：未达到次数上限则重新排队，达到上限则失败。这避免任务永远卡住。

## 9. 当前边界与后续工作

- 扫描版 PDF 没有文字层时会得到 `no_extractable_text`，后续可以加入光学字符识别。
- Windows 本地工作命令用于学习和演示；正式部署仍采用 Linux、Redis 和 Celery。
- 本步只保存完整解析文本。分块、向量生成和 pgvector 写入已经在[第 7 步](07-chunking-and-vector-indexing.md)完成。
- 恶意文档解析最终还应放入资源受限的隔离进程或容器，本步已经先建立大小、页数、展开量和输出字符限制。

## 10. 自动化验证结果

- 45 个测试全部通过。
- 分支覆盖率 82.00%，门槛为 80%。
- 新增 13 个文档摄取相关测试，覆盖三种格式、权限、恶意输入、版本、失败和恢复。
- Alembic 模型与数据库迁移无漂移。
- Ruff 代码规范和格式检查通过。
- Mypy 严格类型检查通过。
- 第三方测试客户端仍有一条已记录的弃用警告，不影响真实网络接口。

## 11. 官方学习资料

- [FastAPI 文件上传与 UploadFile](https://fastapi.tiangolo.com/tutorial/request-files/)
- [PostgreSQL 17 SELECT、FOR UPDATE 与 SKIP LOCKED](https://www.postgresql.org/docs/17/sql-select.html)
- [Python 3.11 hashlib 与 SHA-256](https://docs.python.org/3.11/library/hashlib.html)
- [Python 3.11 zipfile](https://docs.python.org/3.11/library/zipfile.html)
- [pypdf 官方项目](https://pypi.org/project/pypdf/)
- [python-docx 官方项目](https://pypi.org/project/python-docx/)
- [Celery 官方常见问题](https://docs.celeryq.dev/en/stable/faq.html#windows)

## 12. 本步完成标准

- [x] 三种允许格式和 20 MB 默认上限。
- [x] 多层文件校验与路径穿越防御。
- [x] 本地对象存储抽象和不可覆盖对象。
- [x] 不可变版本与 SHA-256 指纹。
- [x] 持久任务状态、领取锁和调度索引。
- [x] 独立工作进程和解析文本预览。
- [x] 暂时错误有限重试、永久错误不重试。
- [x] 陈旧任务恢复和人工重试上限。
- [x] 权限与水平越权测试。
- [x] 迁移、覆盖率、代码规范和类型门禁通过。

下一步内容已经在[第 7 步“文本分块与向量写入”](07-chunking-and-vector-indexing.md)完成。
