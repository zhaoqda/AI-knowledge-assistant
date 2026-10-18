# 双模型单次对照

仅比较已有报告，不发起模型调用。单次结果不能判定稳定性能，也不等于产品准确率。
数据集 SHA-256：f51aa9ff1ce265ddc23f03a20e3e189e90469b81b52bff38365983240611da06
代码 SHA-256：d5f7c3da4a40588012065562507714b9868bec27e72baa9a3c1cbdc2eb4427eb
检索方式：keyword；每组题数：8

| 指标 | deepseek / deepseek-flash | tencent / hy3 |
| --- | --- | --- |
| 预设状态与事实检查通过 | 7 | 8 |
| 引用检查通过题数 | 7 | 7 |
| 未核验题数 | 0 | 0 |
| 服务错误题数 | 0 | 0 |
| 模型调用次数 | 10 | 10 |
| 单题耗时中位数（秒） | 1.013 | 2.225 |

| 题目 | deepseek / deepseek-flash | tencent / hy3 | 人工核查 |
| --- | --- | --- | --- |
| late_approval | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| guest_approval_followup | answered；预设检查未通过 | answered；预设检查通过 | 待核查 |
| purchase_joint_approval | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| read_access_conditions | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| provided_meals | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| no_resolution_promise | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| review_privacy_conditions | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| unknown_personal_amount | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |

人工重点：适用条件、例外与否定是否保留；引用虽存在但是否支持结论；冲突是否解释；干扰指令是否被执行。
两组各重复至少三次，并交替运行顺序以减少时间段差异；不据单次结果宣称提升。Token 统计覆盖可能不同，应查看各自原始报告，不能直接把它换算成费用。
