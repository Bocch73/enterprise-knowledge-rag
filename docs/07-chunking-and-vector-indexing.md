# 第 7 步：文本分块与 pgvector 向量写入

## 1. 本步目标

第 6 步已经把 PDF、DOCX 和 Markdown 转换成完整文本。本步继续把全文转换成可以检索的数据：

```text
解析全文 → 按自然边界分块 → 生成 1024 维语义向量 → 原子写入 PostgreSQL → 任务完成
```

本步已经实现：

1. PostgreSQL 17 中启用 pgvector 0.8.6。
2. 使用段落、换行和中英文句末标点优先切分文本。
3. 默认每片最多 800 个字符，相邻片段重叠 120 个字符。
4. 保存片段顺序、全文起止位置、SHA-256 内容指纹和稳定编号。
5. 通过小型异步 Provider 接口生成固定 1024 维向量。
6. 本地默认实现不需要联网、模型下载或密钥，结果可重复。
7. 解析文本、全部片段、全部向量和完成状态在一个数据库事务中提交。
8. 工作进程记录分块、向量化和写入阶段，失败后不会留下半套有效结果。
9. 提供受权限保护的片段分页接口，但不向前端返回原始向量数组。

## 2. 新名词解释

### 文本分块

文本分块是把长文档切成较短片段。检索时通常寻找相关片段，而不是把整本手册都交给模型。片段太大容易混入无关内容，片段太小又会丢失上下文，所以大小必须通过后续评测调整。

### 重叠窗口

相邻片段共享一小段文字，称为重叠窗口。它降低答案跨越切分边界后被拆散的风险，代价是增加片段数量、向量生成量和存储空间。

### 源文本位置

`start_offset` 和 `end_offset` 表示片段在解析全文中的起止字符位置。本项目保证 `content == parsed_text[start_offset:end_offset]`，以后可以用它生成可核对的引用。

### 向量表示

向量表示又称 Embedding，是一组浮点数。真实语义模型经过训练后，会让含义相近的文本在向量空间中更接近。本项目数据库列固定为 `vector(1024)`，即每条片段向量必须包含 1024 个数。

### 向量提供者

Provider 是能力接口。工作进程只要求“输入多段文本，按原顺序返回同样数量的 1024 维向量”，业务代码不直接依赖某个供应商。当前运行实现调用阿里云百炼的 `qwen3.7-text-embedding`，测试环境使用不联网的确定性替身。

### 精确向量检索

精确检索会计算符合条件的全部向量距离，再取最接近的结果。它结果准确、适合小数据基线，但数据增大后查询成本会上升。

### 近似向量索引

近似索引用额外数据结构加速最近邻搜索，可能牺牲少量召回。pgvector 支持分层可导航小世界图和倒排文件两类近似索引。本项目先保留精确检索基线，等第 11 步有真实评测和规模数据后再决定是否创建近似索引。

### 数据回填

数据回填是为历史记录补上新版本需要的数据。迁移 `20260828_0003` 会把旧的解析完成任务重新排队，使升级后的工作进程为旧文档生成片段和向量。

## 3. 分块规则

默认配置位于 `.env.example`：

```dotenv
RAG_CHUNK_SIZE_CHARACTERS=800
RAG_CHUNK_OVERLAP_CHARACTERS=120
```

算法先尝试在窗口后 40% 范围内寻找自然边界，优先级包括空段、换行、中英文句末标点；找不到时才在最大长度处强制切分。每个片段都保存：

- `chunk_index`：从 0 开始的文档内顺序。
- `content`：片段原文。
- `start_offset`、`end_offset`：在解析全文中的位置。
- `content_sha256`：片段内容指纹。
- `embedding_model`：生成向量的实现或模型标识。
- `embedding_dimensions`：维度，当前固定为 1024。
- `embedding`：PostgreSQL 的 `vector(1024)` 数据。

字符分块实现简单、对中英文都可预测，但字符数不等于模型令牌数。接入真实模型后，应结合该模型的分词器和评测数据决定是否升级为令牌感知或文档结构感知分块。

## 4. 生产语义模型与测试替身

正式运行时使用阿里云百炼 `qwen3.7-text-embedding`。文档以 `document` 类型批量向量化，用户问题以 `query` 类型向量化并附带英文任务说明。两种类型不能共用缓存键，因为同一文本在不同任务下可能返回不同向量。

`test-deterministic-embedding-v1` 仅在自动化测试环境中使用，它有三个用途：

1. 自动化测试不依赖网络和付费密钥。
2. 相同输入在不同运行中产生相同结果，故障容易复现。
3. 可以真实验证 pgvector 类型、写入、距离计算和任务幂等性。

测试替身没有经过语义训练，不能代表生产检索质量。正式模型上线后仍必须使用固定评测集比较召回率、延迟和费用；文档片段会发送给阿里云百炼，因此生产部署还要完成数据分类、供应商协议和地域合规评审。

## 5. 数据库与事务设计

初始迁移 `20260828_0003` 新增 `document_chunks` 表；迁移 `20260830_0007` 将向量升级为1024维并增加余弦距离 HNSW 近似索引。任务阶段为：

```text
queued → parsing → chunking → embedding → indexing → completed
                                                    └→ failed
```

片段表使用文档版本外键和级联删除。`document_version_id + chunk_index` 唯一，数据库会拒绝同一版本的重复序号。片段公开编号根据版本编号、序号和内容指纹稳定生成；相同内容重做任务时编号不变。

写入前会检查向量数量、维度以及是否包含非有限数。最终事务先更新解析文本，删除该版本旧片段，再写入全套新片段，最后把任务标记完成。任何一步失败都会回滚整个事务。

## 6. 当前接口

| 方法与路径 | 权限 | 用途 |
|---|---|---|
| `GET /api/v1/documents/versions/{version_id}/chunks` | 所有者、编辑者 | 分页查看有序片段及向量元数据 |

查询参数：

- `offset`：跳过多少个片段，默认 0。
- `limit`：最多返回多少个片段，默认 20，最大 100。

响应不会包含 `embedding` 数组。普通查看者目前不能读取完整片段，避免绕过后续检索权限和最小披露规则。

## 7. 亲手体验

### 终端一：启动接口

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.server --reload
```

在 Chrome 地址栏打开 <http://127.0.0.1:8000/docs>，不要粘贴到 Google 搜索框。

### 终端二：运行工作进程

上传文档后运行：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.cli.process_ingestion_jobs --max-jobs 10
```

回到接口页面：

1. 查询摄取任务，确认 `status=completed`、`stage=completed`、`progress=100`。
2. 复制上传结果中的版本编号。
3. 调用 `GET /api/v1/documents/versions/{version_id}/chunks`。
4. 检查片段顺序、位置、1024维元数据和模型标识。

也可以在 pgAdmin 4 中执行只读验证：

```sql
SELECT
    document_version_id,
    chunk_index,
    character_count,
    embedding_model,
    vector_dims(embedding) AS dimensions
FROM document_chunks
ORDER BY document_version_id, chunk_index
LIMIT 20;
```

## 8. 自动化验证结果

- 50 个测试全部通过。
- 分支覆盖率 82.33%，门槛为 80%。
- pgvector 数据库扩展版本为 0.8.6。
- Python pgvector 映射库版本为 0.5.0。
- 开发库和测试库迁移版本均为 `20260828_0003`。
- 数据库列已验证为 `vector(1024)`。
- Alembic 模型与迁移无漂移。
- Ruff 格式和代码规范检查通过。
- Mypy 严格类型检查通过。
- 第三方测试客户端仍有一条已记录的弃用警告，不影响真实网络接口。

## 9. 官方学习资料

- [pgvector 官方项目与查询说明](https://github.com/pgvector/pgvector)
- [pgvector-python 官方 SQLAlchemy 用法](https://github.com/pgvector/pgvector-python#sqlalchemy)
- [PostgreSQL CREATE EXTENSION](https://www.postgresql.org/docs/17/sql-createextension.html)
- [SQLAlchemy 会话与事务](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Python hashlib 与 SHA-256](https://docs.python.org/3.11/library/hashlib.html)
- [Python Protocol 结构化类型](https://docs.python.org/3.11/library/typing.html#typing.Protocol)

## 10. 本步完成标准

- [x] 两个数据库启用 pgvector 0.8.6。
- [x] 自然边界优先的可配置字符分块。
- [x] 相邻重叠、全文位置和内容指纹。
- [x] 1024维向量 Provider 抽象、百炼运行实现和离线测试替身。
- [x] `vector(1024)` 持久化、HNSW索引与距离运算验证。
- [x] 原子写入、稳定片段编号和重复执行幂等。
- [x] 历史解析任务回填策略。
- [x] 分块阶段进度和受权限保护的查看接口。
- [x] 全量测试、覆盖率、类型、代码规范和迁移门禁通过。

下一步是第 8 步“混合检索”：实现向量召回、PostgreSQL 关键词全文检索、知识库权限过滤和倒数排名融合，并用固定问题集评估结果。
