---
id: automation/hermes-skills
dimension: 自动化编排
level_edge: L1->L2
type: demo
env: container
verify:
  - cmd: "hermes skills --help >/dev/null 2>&1"
    expect_exit: 0
---

# 技能库：团队沉淀的做法

```bash
hermes skills list
hermes -s posthog-analysis chat -q "这个月的 DAU 趋势"
```

Skill 是**团队资产**，不是个人配置。加载一个 skill 后 agent 的行为会变——
它按团队沉淀的做法干活，而不是每次从零发挥。

发现技能过时或漏步骤，**当场 `skill_manage` 修掉**，别憋着等别人踩同一个坑。
