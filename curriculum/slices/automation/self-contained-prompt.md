---
id: automation/self-contained-prompt
dimension: 自动化编排
level_edge: L1->L2
type: pitfall
env: own-mac
---

# cron 的 prompt 必须自包含

它运行在一个**全新会话**里，没有你刚才说的话、没有当前目录、没有上下文。

在交互式会话里能跑通的 prompt，直接搬进 cron 十有八九失败。
写 cron prompt 时假设读它的人（agent）什么都不知道。
