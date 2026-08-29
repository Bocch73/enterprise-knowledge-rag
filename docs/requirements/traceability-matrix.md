# 需求追踪矩阵

需求追踪矩阵把业务需求、负责模块、架构决策和验证证据连起来。已实现范围填写当前自动化测试，未实现范围仍填写计划证据，不能把未来计划误认为已经完成。

| 需求范围 | 负责模块 | 主要架构决策 | 计划验证证据 |
|---|---|---|---|
| FR-AUTH、FR-KB | identity、knowledge_base、frontend | ADR-0001、ADR-0002 | 后端身份与权限测试；前端 `auth.spec.ts`、`workspace.spec.ts` |
| FR-DOC | document、ingestion、indexing、frontend | ADR-0001、ADR-0002、ADR-0004、ADR-0005 | `test_document_ingestion.py`、`test_indexing.py`；前端上传与任务组件 |
| FR-RET | retrieval、indexing、evaluation | ADR-0002、ADR-0003、ADR-0004 | `test_indexing.py`、`test_retrieval.py`；版本化固定数据集、Top K 命中率、召回率、平均倒数排名和归一化折损累计增益报告 |
| FR-CHAT | answers、generation、retrieval、frontend、evaluation | ADR-0003、ADR-0004 | 后端 `test_answers.py`、`test_generation.py`；前端流解析、引用组件与 Chrome 流程；引用、事实覆盖和拒答指标；待补多轮会话 |
| FR-EVAL | evaluation | ADR-0003、ADR-0004 | `test_evaluation.py`；数据集与语料 SHA-256 指纹；逐题原始输出；检索及确定性完整参考报告；质量门禁 |
| FR-AUDIT、FR-OPS | audit、operations | ADR-0001、ADR-0005、ADR-0006 | `test_operations.py`：审计持久化、过滤、普通用户拒绝、全局任务队列、指标端点；健康检查与日志测试 |
| NFR-SEC | 所有模块 | 全部 | 权限矩阵、限流与监控令牌测试、安全响应头、审计敏感字段断言；待补自动密钥扫描与模糊测试 |
| NFR-PERF | retrieval、chat、operations | ADR-0002、ADR-0003 | 固定环境负载测试报告 |
| NFR-REL | ingestion、repositories、delivery | ADR-0002、ADR-0005、ADR-0007 | 重复投递、事务回滚、持续工作进程批量测试、备份与恢复演练脚本；待执行真实恢复演练 |
| NFR-OBS | operations、audit | ADR-0001、ADR-0004、ADR-0005、ADR-0006 | `test_operations.py`：请求、检索、模型、缓存、限流与任务指标；审计请求编号；待补分布式追踪 |
| NFR-DEP | delivery、operations、frontend、backend | ADR-0005、ADR-0006、ADR-0007 | `quality-gates.yml`、`release.yml`、前后端 Dockerfile、`compose.production.yml`、`test_deployment_assets.py`、部署与回滚手册；待执行真实容器和服务器演练 |
