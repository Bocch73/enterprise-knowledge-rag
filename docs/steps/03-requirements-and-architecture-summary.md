# 第 3 步总结：需求与总体架构

## 本步完成内容

- 建立带编号、优先级和验收条件的功能需求。
- 建立安全、性能、可靠性、恢复、可观测性和维护性目标。
- 编写 10 个核心“给定—当—那么”验收场景。
- 设计系统上下文、可部署单元、模块依赖、文档摄取和问答数据流。
- 明确 PostgreSQL 是业务数据唯一可信来源，Redis 只用于缓存和任务消息。
- 记录 5 项正式架构决策及重新评估条件。
- 建立需求、模块、架构决策和未来测试之间的追踪矩阵。

## 已接受的关键决定

1. 使用模块化单体，不一开始拆微服务。
2. 使用 PostgreSQL 17 + pgvector 0.8 系列，不使用现有 SQL Server 2008 R2。
3. 默认采用关键词与向量混合检索，通过倒数排名融合候选。
4. 生成、向量和重排模型通过小型 Provider 接口接入。
5. 正式文档摄取采用数据库任务记录、Redis 消息代理和 Linux Celery 工作进程。
6. 数据量小时先建立精确向量检索基线，再用真实评测决定是否启用 HNSW 近似索引。

## 必须掌握的知识点

1. 功能需求描述系统行为，非功能需求描述系统运行质量。
2. 验收条件必须可观察、可测试，不能只写“体验良好”或“性能优秀”。
3. 架构决策记录保存背景和代价，而不是只保存技术名称。
4. Redis 是可丢失后重建的加速层，不能成为业务数据唯一可信来源。
5. 权限过滤必须在检索和模型调用之前完成，不能只在页面隐藏按钮。
6. 异步任务消息可能重复，因此任务处理必须幂等，最终状态以数据库为准。
7. 近似向量索引用少量召回损失换取速度，是否使用必须由评测决定。
8. 性能目标与实测结果必须明确区分。

## 自我检查

进入下一步前，尝试不用文档回答：

1. 为什么当前采用模块化单体？
2. 为什么不使用现有 SQL Server 2008 R2？
3. PostgreSQL 和 Redis 分别保存什么？
4. 为什么关键词和向量检索要融合？
5. 文档任务为什么必须幂等？
6. 权限过滤放在模型调用之后会造成什么风险？

## 本步文档

- [功能需求](../requirements/functional-requirements.md)
- [非功能需求](../requirements/non-functional-requirements.md)
- [核心验收场景](../requirements/acceptance-scenarios.md)
- [需求追踪矩阵](../requirements/traceability-matrix.md)
- [系统总体架构](../architecture/system-architecture.md)
- [技术栈与职责](../architecture/technology-stack.md)
- [架构决策记录](../architecture/decisions/README.md)
- [第 3 步面试题](../interview/03-requirements-and-architecture.md)

## 官方资料

- [FastAPI 功能](https://fastapi.tiangolo.com/features/)
- [PostgreSQL 全文检索](https://www.postgresql.org/docs/current/datatype-textsearch.html)
- [pgvector](https://github.com/pgvector/pgvector)
- [Celery 任务队列](https://docs.celeryq.dev/en/stable/getting-started/introduction.html)
- [Vue 3 指南](https://vuejs.org/guide/introduction.html)
