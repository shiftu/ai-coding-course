---
id: quality/auto-review
dimension: 质量验证
level_edge: L1->L2
type: exercise
env: container
---

# 提交前让 agent 审自己的 diff

拿一个"看起来没问题"的 diff 让 agent 按 review 流程审——典型能揪出安全漏洞、
魔法数字、日志泄漏这类机械问题。

**练习**：提交前让 agent 评审自己的 diff，把问题修掉，记录
"AI 审出 N 个，人工又发现 M 个"。这个比例你要心里有数。

**自动 review 能抓约 80% 的机械问题，但业务语义正确性只能人来判断。**
