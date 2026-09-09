---
id: tool/plan-before-code
dimension: 工具操作
level_edge: L1->L2
type: exercise
env: container
---

# 先要计划，再放它写

完整工作循环：**给需求 → 审计划 → 看着它实现 → 自己验证 → 提交 PR**。

```bash
git checkout -b feat/dedup     # 先开分支
claude                          # 或 codex
```

进去第一件事不是"帮我实现 X"，而是**先让它讲计划**（Claude Code 用 plan 模式，
Codex 用 `--approval-mode`）。看到计划后你才有机会说"这里范围大了，先做输入和去重，
统计放 V2"。

**分段放行**：先核心函数，验收后再补 CLI 入口。别让它一口气写完 300 行再回来。
