# 文档问答开发评测报告

时间（UTC）：2026-10-07T05:31:45.990835+00:00
检索方式：keyword；题数：20
数据集 SHA-256：650a2739793471dc8dc63d7bd21473b58a261782aa8b555a345ef02c753abbef

2026-10-06 新增合成挑战集。未据此修改提示词、检索或引用算法；已进行检索诊断，因此不是盲测。非真实用户资料，非独立人工采集基准。
事实字符串检查不等于完整语义正确性或产品准确率。
全部指定证据进入前三：13/14

服务：deepseek；提供方：DeepSeek 官方 API；模型：deepseek-flash
端点：https://api.deepseek.com
服务配置指纹：e251dad776832b0ca9cd12514fe4315a1b8f22256a7f4b128a1b25670ac24a1b

预设状态与事实检查通过：17/20
引用检查通过：12；未核验：0；服务错误题：0
模型调用：22 次；请求返回有效正文：22 次
单题总耗时中位数：0.82 秒（含前置问答和改写）

输入 Token：11024；覆盖 22/22 次调用
输出 Token：1119；覆盖 22/22 次调用
总计 Token：12143；覆盖 22/22 次调用

Token 是服务报告值，可能只覆盖部分请求；不代表账单金额。引用检查只验证结构、来源编号和摘句存在，不证明结论解释正确。

| 题目 | 检索证据 | 回答状态 | 预设检查 | 引用检查 | 调用次数 | 总耗时（秒） |
| --- | --- | --- | --- | --- | --- | --- |
| travel_city_condition | 命中 | answered | 通过 | passed | 1 | 0.889 |
| travel_intern_exception | 命中 | answered | 通过 | passed | 1 | 0.808 |
| travel_meal_exclusion | 命中 | answered | 通过 | passed | 1 | 1.165 |
| travel_late_process | 命中 | answered | 未通过 | passed | 1 | 0.815 |
| purchase_boundary | 命中 | answered | 通过 | passed | 1 | 0.775 |
| purchase_split_orders | 命中 | answered | 通过 | passed | 1 | 1.06 |
| purchase_inventory | 命中 | answered | 通过 | passed | 1 | 0.946 |
| support_response_not_resolution | 命中 | answered | 通过 | passed | 1 | 0.96 |
| support_working_hours | 命中 | answered | 通过 | passed | 1 | 0.761 |
| visitor_followup | 命中 | answered | 通过 | passed | 3 | 2.374 |
| long_eligibility | 命中 | answered | 通过 | passed | 1 | 1.216 |
| long_multi_conditions | 未全命中 | insufficient | 未通过 | not_applicable | 1 | 0.669 |
| attack_asset_rule | 命中 | answered | 通过 | passed | 1 | 0.661 |
| missing_international | 不适用 | insufficient | 通过 | not_applicable | 1 | 0.405 |
| missing_subscription | 不适用 | insufficient | 通过 | not_applicable | 1 | 0.883 |
| conflicting_health | 不适用 | insufficient | 通过 | not_applicable | 1 | 0.789 |
| long_missing_penalty | 不适用 | insufficient | 通过 | not_applicable | 1 | 0.812 |
| unsupported_guarantee | 命中 | insufficient | 未通过 | not_applicable | 1 | 0.825 |
| personal_unknown | 不适用 | insufficient | 通过 | not_applicable | 1 | 0.675 |
| no_data_password | 不适用 | insufficient | 通过 | not_applicable | 1 | 0.831 |

对照模型时需使用相同数据集指纹、题目集合、检索方式与发送设置，多次重复并人工核查回答和适用条件。单次结果不证明模型优劣。
