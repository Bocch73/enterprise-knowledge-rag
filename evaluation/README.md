# RAG 质量评测资产

这个目录保存可审查、可重复的检索增强生成（Retrieval-Augmented Generation）评测证据。语料、标签和报告与业务代码分开，产品或领域人员无需阅读 Python 也能检查问题和正确来源。

## 目录结构

- `fixtures/`：9 份完全虚构的企业制度文档，不含真实公司或个人信息。
- `datasets/company-policy-v1.json`：版本为 `2.0.0` 的固定数据集，共 135 个问题，其中 108 个可回答、27 个应拒答。
- `reports/reference-deterministic-full-v2.json`：不联网的完整回归报告，用于持续集成。
- `reports/reference-qwen37-rerank-deepseek-v4-flash-full-v2.json`：真实调用 Qwen 嵌入、Qwen 重排和 DeepSeek 生成的端到端报告。

不要把生产文档放进本目录。真实企业资料必须使用经过审批的私有位置，并确认资料能否发送给外部模型服务。

## 两种实验分别证明什么

### 不联网回归实验

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-reference-evaluation.ps1 `
  -Mode full `
  -EmbeddingProvider deterministic `
  -RerankProvider deterministic `
  -GenerationProvider deterministic `
  -Output .\evaluation\reports\reference-deterministic-full-v2.json
```

`deterministic` 表示“同样输入永远得到同样结果”的本地测试替身。它不调用外部模型、不产生费用，适合每次改代码后做稳定回归；它不能证明真实模型效果。

### 真实端到端实验

先在被 Git 忽略的 `backend/.env.deepseek` 中配置 `DASHSCOPE_API_KEY` 和 `DEEPSEEK_API_KEY`，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-reference-evaluation.ps1 `
  -Mode full `
  -EmbeddingProvider configured `
  -RerankProvider configured `
  -GenerationProvider configured `
  -Output .\evaluation\reports\reference-qwen37-rerank-deepseek-v4-flash-full-v2.json
```

这条命令会把本目录的虚构文档和问题发送给模型提供商，并产生少量接口费用。程序只允许操作名称以 `_test` 结尾的隔离数据库。

## 报告记录内容

报告模式为 `2.0`，除逐题结果外，还保存：

- 文本分块大小与重叠字符数；
- 每路召回候选数量、倒数排名融合常数、最终 `Top K`；
- 嵌入、重排、生成模型名与向量维度；
- 证据充分性阈值、上下文预算、温度和最大输出词元；
- 提示词版本和费用单价快照；
- 每次外部调用的阶段、提供商、模型、调用编号、词元数、尝试次数、延迟、成功状态和估算费用；
- 检索、证据判断、引用、拒答、关键事实覆盖与延迟指标。

费用是依据报告中的单价快照和返回词元数计算的估算值，账单仍以提供商控制台为准。报告不写入密钥、访问令牌、完整提示词或完整文档内容。

## 当前真实基准

真实端到端报告共评测 135 个问题，质量门禁通过：

| 指标 | 结果 |
|---|---:|
| Top 5 命中率 | 1.000000 |
| 平均倒数排名 | 0.995370 |
| Top 5 归一化折损累计增益 | 0.996583 |
| 证据充分性判断准确率 | 0.992593 |
| 可回答问题接受率 | 1.000000 |
| 不可回答问题拒绝率 | 0.962963 |
| 引用准确率 / 引用召回率 | 0.992593 / 0.992593 |
| 关键事实覆盖率 | 0.952160 |
| 检索延迟第 95 百分位 | 1318.747 毫秒 |
| 回答延迟第 95 百分位 | 4196.069 毫秒 |

本次记录 658 次外部调用，调用编号缺失数为 0，估算费用为人民币 0.166909 元和美元 0.013720104 元。这里的两种币种不能直接相加。

## 如何解读边界

135 个问题比原来的小样本更适合回归，但它们仍来自 9 份短小虚构文档。结果不能证明系统已经适合任意真实企业数据、复杂表格、扫描件、超长文档或生产并发。当前报告里仍有一个生成失败样本和一个证据判断误接受样本，逐题记录保留了这些失败，便于下一轮有针对性地改进。

## 官方资料

- [阿里云百炼文本重排接口](https://help.aliyun.com/zh/model-studio/text-rerank-api)
- [阿里云百炼文本向量接口](https://help.aliyun.com/zh/model-studio/embedding?disableWebsiteRedirect=true)
- [DeepSeek 错误码](https://api-docs.deepseek.com/quick_start/error_codes/)
- [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)
