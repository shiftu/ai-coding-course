---
id: automation/keep-error-alert
dimension: 自动化编排
level_edge: L1->L2
type: pitfall
env: own-mac
---

# 非零退出会告警，这是特性别关掉

自动化也要有兜底。任务非零退出发错误告警，是为了让你**及时发现 broken watchdog**。

关掉它，你的监控就变成了"沉默地不工作"。
