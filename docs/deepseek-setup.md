# 混元与 DeepSeek 联调

状态：2026-10-07 已完成本机真实接入及单次双模型 20 题联调，见 [对照报告](../evaluation/model-comparison-2026-10-07.md) 与 [复核记录](../evaluation/model-review-2026-10-07.md)。没有真实用户评测或稳定性结论。

当前本地项目已经设置服务清单路径并保留原腾讯配置，本机密钥已配置；下列复制配置步骤供其他机器重新部署时使用。

## 配置

1. 在 [DeepSeek 开放平台](https://platform.deepseek.com/) 创建 API Key，根据需要准备调用余额。网页或应用会员不应当作已配置的 API 凭证。
2. 在本项目 `.env` 中添加 `DEEPSEEK_API_KEY=你的密钥`，不要把密钥发送到聊天或提交 Git。
3. 复制 `model_services.example.json` 为 `model_services.json`。保留实际要使用的 `tencent` 和 `deepseek` 两项，替换腾讯示例地址为现有真实地址；删除企业占位配置。这一步只编辑新配置文件，不覆盖原来的腾讯密钥。
4. 在 `.env` 中设置 `MODEL_SERVICES_CONFIG` 为 `model_services.json` 的绝对路径。重新启动应用让部署配置生效。

DeepSeek 示例使用 `https://api.deepseek.com`、`deepseek-flash`，并设置 `thinking_disabled=true`，用于普通文档问答而非额外推理预算。当前模型名和思考参数依据 [首次调用](https://api-docs.deepseek.com/guides/codex)、[更新记录](https://api-docs.deepseek.com/updates/) 和 [思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)；若平台调整接口或账户不可用，以官方控制台和文档为准。示例配置存在不代表企业已经批准该服务。

## 先检查一道虚构题

```bash
python evaluation/run.py --dataset evaluation/challenge_cases.json --mode keyword --answers --service deepseek --allow-model-send --limit 1 --output evaluation/deepseek-smoke.json --markdown-output evaluation/deepseek-smoke.md
```

明确允许发送所选数据集资料和问答；这是真实计费请求。检查服务名、模型、请求状态、引用核验、回答条件和调用次数。不能仅因 HTTP 成功认定接入完成；若正文为空或被截断，需要检查接口参数。

## 完整对照

用同一版代码、同一批题和同一检索方式，各跑一份新报告：

```bash
python evaluation/run.py --dataset evaluation/challenge_cases.json --mode keyword --answers --service tencent --allow-model-send --output evaluation/challenge-tencent.json --markdown-output evaluation/challenge-tencent.md
python evaluation/run.py --dataset evaluation/challenge_cases.json --mode keyword --answers --service deepseek --allow-model-send --output evaluation/challenge-deepseek.json --markdown-output evaluation/challenge-deepseek.md
python evaluation/compare.py evaluation/challenge-tencent.json evaluation/challenge-deepseek.json --output evaluation/model-comparison.md
```

对照工具只读取已有报告，不调用模型。数据集、代码、题目顺序或检索方式不同会拒绝比较。两组至少各重复三次，使用新的结果文件名保存，并交替运行顺序；当前对照报告是一次一对，不把重复结果自动当统计显著性。

参考 `evaluation/challenge-human-review.md` 人工检查条件、否定、冲突和干扰指令。不要根据这批题修改模型提示词后继续称它为盲测；后续调试后应把它归入回归集，另留新题。

## 当前还缺什么

本机基础联调已完成；其他部署仍需独立配置密钥、服务清单和网络。后续还需要重复模型评测、处理已发现的条件遗漏与长文检索缺口，并开展真实用户任务测试。没有用户成功率、服务商安全保证或成本提升结论。Token 统计来自服务报告，不等于账单金额。
