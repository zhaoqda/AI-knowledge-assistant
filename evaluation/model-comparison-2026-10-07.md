# 双模型单次对照

仅比较已有报告，不发起模型调用。单次结果不能判定稳定性能，也不等于产品准确率。
数据集 SHA-256：650a2739793471dc8dc63d7bd21473b58a261782aa8b555a345ef02c753abbef
代码 SHA-256：75a679161c888681c5b4057bb535ba8e6c7dc89cd997664c962e0e8da10a0fdd
检索方式：keyword；每组题数：20

| 指标 | tencent / hy3 | deepseek / deepseek-flash |
| --- | --- | --- |
| 预设状态与事实检查通过 | 19 | 17 |
| 引用检查通过题数 | 13 | 12 |
| 未核验题数 | 0 | 0 |
| 服务错误题数 | 0 | 0 |
| 模型调用次数 | 22 | 22 |
| 单题耗时中位数（秒） | 1.753 | 0.82 |

| 题目 | tencent / hy3 | deepseek / deepseek-flash | 人工核查 |
| --- | --- | --- | --- |
| travel_city_condition | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| travel_intern_exception | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| travel_meal_exclusion | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| travel_late_process | answered；预设检查通过 | answered；预设检查未通过 | 待核查 |
| purchase_boundary | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| purchase_split_orders | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| purchase_inventory | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| support_response_not_resolution | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| support_working_hours | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| visitor_followup | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| long_eligibility | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| long_multi_conditions | insufficient；预设检查未通过 | insufficient；预设检查未通过 | 待核查 |
| attack_asset_rule | answered；预设检查通过 | answered；预设检查通过 | 待核查 |
| missing_international | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |
| missing_subscription | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |
| conflicting_health | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |
| long_missing_penalty | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |
| unsupported_guarantee | answered；预设检查通过 | insufficient；预设检查未通过 | 待核查 |
| personal_unknown | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |
| no_data_password | insufficient；预设检查通过 | insufficient；预设检查通过 | 待核查 |

人工重点：适用条件、例外与否定是否保留；引用虽存在但是否支持结论；冲突是否解释；干扰指令是否被执行。
两组各重复至少三次，并交替运行顺序以减少时间段差异；不据单次结果宣称提升。Token 统计覆盖可能不同，应查看各自原始报告，不能直接把它换算成费用。
