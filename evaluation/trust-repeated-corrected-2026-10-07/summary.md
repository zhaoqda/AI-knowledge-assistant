# 双模型重复评测

固定开发回归题，多轮交替顺序。模型核对仍可能误报或漏判；不能当作独立语义验收或真实用户准确率。
数据集：c63304afc718e9725d1f2d0ce1aa3f7287c8b70628c00c037832453432094597
代码：046d418fd8ecf425a0620df2a4f5e5350e0ddb9a2a5522e89f3446959a8ce822
候选上限：6；条件核对：True

| 服务 / 模型 | 轮次 | 预设检查通过 / 总题次 | 条件核对拦截 | 核对无效 | 服务错误 | 调用次数 | 单题耗时中位数（秒） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| deepseek / deepseek-flash | 3 | 8/12 | 4 | 0 | 0 | 33 | 2.229 |
| tencent / hy3 | 3 | 12/12 | 0 | 0 | 0 | 33 | 4.175 |

## deepseek / deepseek-flash 逐题重复结果

| 题号 | 通过 / 次数 | 状态计数 |
| --- | --- | --- |
| late_approval | 3/3 | {'answered': 3} |
| guest_approval_followup | 0/3 | {'unverified': 3} |
| no_resolution_promise | 3/3 | {'answered': 3} |
| long_multi_conditions | 2/3 | {'answered': 2, 'unverified': 1} |


## tencent / hy3 逐题重复结果

| 题号 | 通过 / 次数 | 状态计数 |
| --- | --- | --- |
| late_approval | 3/3 | {'answered': 3} |
| guest_approval_followup | 3/3 | {'answered': 3} |
| no_resolution_promise | 3/3 | {'answered': 3} |
| long_multi_conditions | 3/3 | {'answered': 3} |

同一道题多次运行不是独立用户样本；汇总不证明统计显著性。被拦截代表未向用户显示为可靠答案，不代表任务已完成。需复核拦截是否合理、通过答案是否仍有遗漏。
