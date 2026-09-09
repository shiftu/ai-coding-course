---
id: automation/webhook-subscribe
dimension: 自动化编排
level_edge: L2->L3
type: demo
env: own-mac
---

# 事件订阅：webhook 触发

定时任务是"按时间"，事件订阅是"按发生"。webhook 订阅外部事件源，
事件到达时 agent 自动处理并回复。

投递配置要想清楚：回当前会话（origin）/ 指定飞书群 / 失败时告警到哪。
