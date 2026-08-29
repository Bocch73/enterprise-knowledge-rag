# 第 8 步：权限安全的混合检索与倒数排名融合

## 1. 本步目标

本步把第 7 步保存的片段真正变成可查询结果。一次搜索同时执行两条路线：

```text
用户问题
├─ pgvector 余弦距离：按向量方向寻找相近片段
└─ PostgreSQL 全文检索：按关键词、编号和短语寻找片段
                 ↓
            倒数排名融合
                 ↓
       统一排序并返回可引用元数据
```

本步已经实现：

1. `POST /api/v1/knowledge-bases/{id}/search` 混合检索接口。
2. 每次检索先验证调用者是该知识库成员。
3. 两路数据库查询都限定知识库编号，防止跨知识库泄露。
4. 只检索每个逻辑文档版本号最高且处理成功的版本。
5. pgvector 精确余弦距离候选。
6. PostgreSQL 存储生成的 `tsvector` 搜索列和广义倒排索引。
7. 对普通用户输入使用不会产生查询语法错误的 `websearch_to_tsquery`。
8. 使用倒数排名融合合并两路名次，并返回透明的排名与原始分数。
9. 查看者可以获得检索所需片段，但仍不能调用完整分块浏览接口。

## 2. 新名词解释

### 全文检索

全文检索不是简单地查找字符串是否出现。数据库先把文档解析成规范化词项，再把用户问题转换成查询结构，支持多个词语、短语、排除词和相关性排序。

### `tsvector`

`tsvector` 是 PostgreSQL 保存文档搜索词项及位置信息的数据类型。本项目的 `search_vector` 根据片段 `content` 自动生成，业务代码不能手工写入，因此原文变化时搜索表示会由数据库自动同步。

### `tsquery`

`tsquery` 是 PostgreSQL 对用户搜索条件的结构化表示。项目使用 `websearch_to_tsquery`，它接受普通文本、引号短语、`OR` 和减号排除语法，并且不会因为用户输入特殊符号而抛出语法错误。

### 广义倒排索引

Generalized Inverted Index，常简称 GIN。它保存“词项对应哪些数据库行”的映射。PostgreSQL 官方推荐它作为全文检索的首选索引类型。索引提升读取速度，但会占用空间并增加片段写入成本。

### 余弦距离

余弦距离衡量两个向量方向的差异。pgvector 使用 `<=>` 运算符；距离越小，方向越接近。对于非零向量，余弦相似度可以用 `1 - 余弦距离` 得到。

### 候选召回

每条检索路线先取一个比最终结果更大的候选集合。本项目每路默认取 30 条，再融合后返回默认前 5 条。候选太少可能漏掉相关内容，太多则增加数据库、融合和后续重排成本。

### 倒数排名融合

Reciprocal Rank Fusion，常简称 RRF。对于某一路的第 `rank` 名，贡献分数为：

```text
1 / (k + rank)
```

本项目默认 `k=60`。同一片段如果在向量和关键词两路都靠前，会得到两份贡献。它只使用名次，不要求余弦距离和全文相关性分数处于同一数值范围。

### 召回

召回表示从全部片段中找出一批可能相关候选。召回阶段追求不要漏掉正确证据，后续可以再使用重排提高前几名精度。

## 3. 为什么使用混合检索

向量路线和关键词路线擅长的问题不同：

| 问题类型 | 向量路线 | 关键词路线 |
|---|---|---|
| 同义表达、自然语言改写 | 真实语义模型通常更强 | 可能因词语不同而漏掉 |
| 制度编号、产品型号 | 可能把精确字符串弱化 | 精确词项通常更强 |
| 人名、缩写 | 取决于模型训练 | 原文出现时稳定 |
| 当前本地确定性向量 | 主要反映词语与字符重合 | 提供真实 PostgreSQL 关键词基线 |

因此当前链路已经真实实现两路查询和融合，但只有接入真实语义向量模型并完成评测后，才能证明同义表达召回能力。

## 4. 最新成功版本规则

一个逻辑文档可以有多个不可变版本。检索不能简单选择版本号最大值，因为最新上传可能仍在解析或向量化。本项目使用窗口函数为每个文档的成功版本排序，只选择版本号最高的一条。

```text
版本 1：completed ← 当前可检索
版本 2：running   ← 暂不暴露

版本 2 完成后：
版本 1：历史保留
版本 2：completed ← 自动成为当前检索版本
```

这实现了无半成品切换，也保留历史版本用于审计。

## 5. 权限边界

检索服务首先调用知识库成员关系检查。无权限和不存在都返回 404，减少编号枚举。随后向量查询和关键词查询都写入 `knowledge_base_id` 条件，形成第二层数据隔离。

所有者、编辑者和查看者都可以检索，因为查看者使用知识库的目的就是读取必要内容；但是查看者仍不能分页浏览整份解析全文或全部片段。这体现最小披露：返回回答所需候选，而不是开放批量导出入口。

## 6. 数据库设计

迁移 `20260828_0004` 为 `document_chunks` 增加：

```sql
search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('simple'::regconfig, content)
    ) STORED
```

并创建：

```sql
CREATE INDEX ix_document_chunks_search_vector
ON document_chunks
USING gin (search_vector);
```

`simple` 配置不做英文词干还原，适合作为多语言不丢词的基础配置，但 PostgreSQL 内置解析器不会为连续中文提供成熟分词。中文企业项目需要评估中文分词扩展、应用侧分词或专用搜索引擎，并用固定数据集验证。

## 7. 当前接口

### 请求

```http
POST /api/v1/knowledge-bases/{knowledge_base_id}/search
Authorization: Bearer <访问令牌>
Content-Type: application/json
```

```json
{
  "query": "SEC-104 passwords",
  "top_k": 5
}
```

- `query`：2 到 500 个字符，首尾与连续空白会被清理。
- `top_k`：最终返回数量，1 到 20，默认 5。

### 响应中的可解释字段

- `fused_score`：倒数排名融合总分。
- `vector_rank`：向量路线名次，未进入该路候选时为 `null`。
- `vector_distance`：余弦距离，越小越相近。
- `keyword_rank`：关键词路线名次。
- `keyword_score`：PostgreSQL 全文相关性分数。
- 文档、版本、片段编号和原文位置：用于后续生成可靠引用。

## 8. 亲手体验

### 终端一：启动接口

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.server --reload
```

在 Chrome 地址栏打开 <http://127.0.0.1:8000/docs>。

### 终端二：处理上传任务

上传至少两份内容不同的文档，然后运行：

```powershell
cd "E:\codex项目\rag1\backend"
.\.venv\Scripts\python.exe -m app.cli.process_ingestion_jobs --max-jobs 10
```

回到接口页面：

1. 点击右上角 `Authorize` 登录。
2. 展开 `retrieval` 分组。
3. 调用 `POST /api/v1/knowledge-bases/{knowledge_base_id}/search`。
4. 输入知识库编号和问题。
5. 检查返回结果的两路名次、融合分数、文档版本和片段位置。

可以在 pgAdmin 4 查看生成的搜索表示：

```sql
SELECT
    chunk_index,
    content,
    search_vector
FROM document_chunks
ORDER BY document_version_id, chunk_index
LIMIT 20;
```

## 9. 自动化验证结果

- 54 个测试全部通过。
- 分支覆盖率 83.45%，门槛为 80%。
- 混合检索新增 4 个核心测试。
- 权限、知识库隔离、特殊字符和最新成功版本切换均通过。
- 开发库和测试库迁移版本均为 `20260828_0004`。
- 生成表达式和广义倒排索引已从数据库元数据验证。
- 第 4 个迁移回退、重新升级和漂移检查通过。
- Ruff 格式和代码规范、Mypy 严格类型、依赖一致性检查通过。
- 第三方测试客户端仍有一条已记录的弃用警告，不影响真实接口。

## 10. 官方学习资料

- [PostgreSQL 17 全文检索控制](https://www.postgresql.org/docs/17/textsearch-controls.html)
- [PostgreSQL 17 表、生成列与全文索引](https://www.postgresql.org/docs/17/textsearch-tables.html)
- [PostgreSQL 17 推荐全文索引类型](https://www.postgresql.org/docs/17/textsearch-indexes.html)
- [PostgreSQL 17 广义倒排索引](https://www.postgresql.org/docs/17/gin.html)
- [pgvector 官方查询与混合检索](https://github.com/pgvector/pgvector#hybrid-search)
- [倒数排名融合原始论文](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)

## 11. 本步完成标准

- [x] 知识库范围混合检索接口。
- [x] 向量精确余弦距离候选。
- [x] 存储生成的全文搜索列和广义倒排索引。
- [x] 安全的普通用户查询解析。
- [x] 倒数排名融合与透明分数。
- [x] 最新成功版本选择。
- [x] 查看者检索和跨知识库隔离。
- [x] 特殊字符、版本切换和融合排序测试。
- [x] 迁移往返、漂移、全量测试和质量门禁。

下一步是第 9 步“带来源引用的问答”：接入真实或兼容的模型 Provider，构建受证据约束的提示词、拒答规则、流式输出和引用校验。
