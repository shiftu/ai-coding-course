---
id: tool/lark-doc
dimension: 工具操作
level_edge: L1->L2
type: exercise
env: own-mac
verify:
  - cmd: "lark-cli --help >/dev/null 2>&1"
    expect_exit: 0
---

# 把产出整理成飞书云文档

```bash
lark-cli doc create ...
```

**练习**：把你第 5 课的 PR 内容整理成一页飞书文档（标题 / 摘要 / 链接），分享给讲师。
