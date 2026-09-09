---
id: tool/hermes-profile
dimension: 工具操作
level_edge: L1->L2
type: exercise
env: container
verify:
  - cmd: "hermes profile --help >/dev/null 2>&1"
    expect_exit: 0
---

# 给自己建独立的 Hermes 配置

```bash
hermes profile create <你的名字>
```

配成内部网关模型。profile 是你的私人工作台——配置、记忆、技能都挂在上面，
和别人隔离。
