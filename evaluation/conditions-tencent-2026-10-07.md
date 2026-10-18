# 文档问答开发评测报告

时间（UTC）：2026-10-07T13:36:44.262093+00:00
检索方式：keyword；题数：8
数据集 SHA-256：f51aa9ff1ce265ddc23f03a20e3e189e90469b81b52bff38365983240611da06

2026-10-07 条件完整性开发回归集，针对此前观察到的条件遗漏设计。新增虚构规则，已用于提示词迭代验证；不是盲测或真实用户基准。状态及事实字符串只覆盖部分完整性条件，仍需语义复核。
事实字符串检查不等于完整语义正确性或产品准确率。
全部指定证据进入前三：7/7

服务：tencent；提供方：腾讯 MaaS；模型：hy3
端点：https://tokenhub.tencentmaas.com/v1
服务配置指纹：0da68840ee2cfd74bc4555331b171a35be3505a7c8a60110681c6e8dcbf16a40

预设状态与事实检查通过：8/8
引用检查通过：7；未核验：0；服务错误题：0
模型调用：10 次；请求返回有效正文：10 次
单题总耗时中位数：2.225 秒（含前置问答和改写）

输入 Token：4901；覆盖 10/10 次调用
输出 Token：840；覆盖 10/10 次调用
总计 Token：5741；覆盖 10/10 次调用

Token 是服务报告值，可能只覆盖部分请求；不代表账单金额。引用检查只验证结构、来源编号和摘句存在，不证明结论解释正确。

| 题目 | 检索证据 | 回答状态 | 预设检查 | 引用检查 | 调用次数 | 总耗时（秒） |
| --- | --- | --- | --- | --- | --- | --- |
| late_approval | 命中 | answered | 通过 | passed | 1 | 2.784 |
| guest_approval_followup | 命中 | answered | 通过 | passed | 3 | 4.498 |
| purchase_joint_approval | 命中 | answered | 通过 | passed | 1 | 2.055 |
| read_access_conditions | 命中 | answered | 通过 | passed | 1 | 2.328 |
| provided_meals | 命中 | answered | 通过 | passed | 1 | 2.032 |
| no_resolution_promise | 命中 | answered | 通过 | passed | 1 | 2.512 |
| review_privacy_conditions | 命中 | answered | 通过 | passed | 1 | 2.122 |
| unknown_personal_amount | 不适用 | insufficient | 通过 | not_applicable | 1 | 1.533 |

对照模型时需使用相同数据集指纹、题目集合、检索方式与发送设置，多次重复并人工核查回答和适用条件。单次结果不证明模型优劣。
