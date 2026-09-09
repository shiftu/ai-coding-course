---
id: automation/first-cron
dimension: 自动化编排
level_edge: L0->L1
type: exercise
env: own-mac
verify:
  - cmd: "hermes cron --help >/dev/null 2>&1"
    expect_exit: 0
---

# 把重复的事变成 cron

```bash
hermes cron create "30 9 * * *"     # 每天 9:30
hermes cron list                     # 确认在列
hermes cron run <ID>                 # 手动触发一次，验证投递
```

**练习**：建一个自己的 cron —— 每天下班前汇总当天 Issue/PR 状态到飞书私聊。
**必须手动触发一次验证投递内容**，别建完就以为成了。
