---
id: automation/delegate
dimension: 自动化编排
level_edge: L2->L3
type: demo
env: container
---

# 委派：把大任务拆给子代理并行跑

`delegate_task` 可以同时开多个子代理干独立的活，比如并行查 3 个仓库的 README 并对比。

适用条件：**任务之间没有依赖**。有依赖的任务并行只会互相打架。
