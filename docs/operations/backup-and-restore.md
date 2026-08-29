# PostgreSQL 备份与恢复手册

## 1. 为什么“有备份文件”仍不算完成

备份成功只证明文件被写出，不能证明文件完整、能够读取、恢复后结构正确或恢复时间满足业务要求。
企业需要定期做恢复演练，并记录恢复点目标和恢复时间目标。

- **恢复点目标**：故障时最多允许丢失多长时间的数据。
- **恢复时间目标**：从故障发生到服务恢复最多允许多长时间。

本项目演示目标仍为恢复点 24 小时、恢复时间 4 小时，尚未经过真实生产数据验证。

## 2. 创建本机备份

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup-postgresql.ps1 `
  -Database enterprise_rag `
  -Username rag_app
```

脚本会安全询问数据库密码，使用 PostgreSQL 17 的 `pg_dump` 创建自定义格式归档，并生成 SHA-256
校验文件。密码只临时放入当前进程环境，结束后立即清除。

默认输出目录是 `deploy/backups`，该目录被 Git 忽略。备份可能包含用户、问题、文档正文和审计数据，
不能提交到公开仓库，也不应保存在与数据库相同的单块磁盘上。

## 3. 为什么选择自定义格式

`pg_dump --format custom` 生成可由 `pg_restore` 读取的归档。与普通 SQL 文本相比，它支持选择对象、
调整恢复顺序和并行恢复，也默认压缩，适合逻辑备份。

逻辑备份不包含本地对象存储中的原文件。完整恢复必须同时备份：

1. PostgreSQL 数据库；
2. `data/objects` 或 Compose 的 `object-storage` 持久卷；
3. 非敏感配置版本；
4. 经过安全管理的密钥；
5. 当前前后端镜像摘要。

## 4. 恢复演练

恢复脚本强制目标数据库名称以 `_restore` 结尾，并拒绝覆盖已经存在的数据库：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore-postgresql-rehearsal.ps1 `
  -BackupPath .\deploy\backups\enterprise_rag-20260829-120000.dump `
  -TargetDatabase enterprise_rag_restore `
  -ConfirmTargetDatabase enterprise_rag_restore
```

脚本依次执行：校验 SHA-256、让 `pg_restore --list` 检查归档、确认目标不存在、创建新数据库、使用
`--exit-on-error` 恢复。它不会删除或覆盖现有数据库。

PostgreSQL 官方提醒：恢复归档可能执行源数据库超级用户创建的代码。来自不可信来源的备份必须先在
隔离环境中检查，不能直接恢复到业务数据库。

## 5. 恢复后的验收

至少检查：

1. `alembic current` 显示预期迁移版本。
2. `SELECT extversion FROM pg_extension WHERE extname = 'vector';` 返回预期 pgvector 版本。
3. 用户、知识库、文档、片段、回答、引用和审计记录数量合理。
4. 随机抽取原文件，重新计算 SHA-256 并与数据库指纹核对。
5. 存活、就绪、登录、检索、回答与引用链路通过。
6. 记录开始时间、结束时间、恢复点、问题和实际恢复时间。

只有恢复演练成功，备份才有可用性证据。

## 6. 保留与安全

演示环境可以从“每日一份、保留 7 天；每周一份、保留 4 周”开始，但实际策略必须依据法规、数据量和
业务风险确定。备份应加密、限制访问、异地保存并定期验证校验值。删除过期备份属于破坏性操作，必须
先确认路径、保留期和至少一个可恢复副本。

## 7. 官方资料

- [PostgreSQL 17：SQL 转储与恢复](https://www.postgresql.org/docs/17/backup-dump.html)
- [PostgreSQL 17：pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
- [PostgreSQL 17：pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)
