---
id: tool/session-manage
dimension: 工具操作
level_edge: L1->L2
type: exercise
env: container
verify:
  - cmd: "hermes sessions --help >/dev/null 2>&1"
    expect_exit: 0
---

# 会话是资产：命名它、找回它

会话不是聊天记录，是可复用的工作上下文。

```bash
hermes sessions list
hermes sessions rename <ID> "第1课-仓库体检"
hermes --continue          # 接着上一个会话
```

**练习**：在 playground 目录跑一次仓库体检，然后给这个会话起个名字。
一周后你还能凭名字找回它——这就是 L2 和 L1 的区别。
