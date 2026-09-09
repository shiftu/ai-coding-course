---
id: automation/health-monitor
dimension: 自动化编排
level_edge: L1->L2
type: exercise
env: own-mac
---

# 状态监控：只报变化，不刷屏

给一个 URL 挂健康检查，服务挂了收到一条 DOWN，恢复了收到一条 UP —— 就这两条。

**练习**：给 playground 的 CI URL 挂健康检查。**建议先让它失败一次**，
确认报警真的会到——没验证过的报警等于没有报警。
