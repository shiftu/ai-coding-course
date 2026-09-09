---
id: quality/confirm-before-write
dimension: 质量验证
level_edge: L1->L2
type: pitfall
env: own-mac
---

# 写操作执行前让它念一遍

发文档、建表格、改配置这类**写操作**，执行前让 agent 把内容念给你听一遍。

读操作错了重来就行，写操作错了要清理——而且可能已经推送给别人了。
