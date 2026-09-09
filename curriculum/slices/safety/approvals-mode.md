---
id: safety/approvals-mode
dimension: safety-gate
level_edge: S2
type: exercise
env: own-mac
---

# 审批三档：manual / smart / off

- **manual** —— 每条都问，新手期用
- **smart** —— 自动放行低风险，拦截高危（`rm -rf` 类）
- **off** —— 不问，只在你完全清楚代价时用

从 manual 起步，熟了切 smart。**别一上来就 off。**
