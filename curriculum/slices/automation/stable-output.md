---
id: automation/stable-output
dimension: 自动化编排
level_edge: L1->L2
type: pitfall
env: own-mac
---

# 监控脚本的输出必须稳定

输出里带时间戳、随机顺序、耗时数字，会让每次 tick 都算"变化" —— 于是天天报警，
于是所有人开始无视报警，于是真出事时没人看。

**监控的价值等于它的信噪比。**
