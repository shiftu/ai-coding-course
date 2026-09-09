---
id: tool/metric-definition-first
dimension: 工具操作
level_edge: L1->L2
type: pitfall
env: own-mac
---

# 看数据先讲口径

New / DAU / 转化在不同团队定义可能不同。**先对齐事件定义，再下结论。**

本公司口径：
- 总 DAU = `Active Action` 事件
- 新用户 = `S-UserRegister`（首次打开自动游客注册）
- 老用户 = 总 - 新

另一个具体的坑：**按 `bot_id` 而不是 `bot_name` 关联事件** —— 同一个 bot 在不同事件类型里名字可能不一致。
