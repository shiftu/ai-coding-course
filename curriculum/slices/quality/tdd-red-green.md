---
id: quality/tdd-red-green
dimension: 质量验证
level_edge: L1->L2
type: exercise
env: container
verify:
  - cmd: "python3 -m pytest --version >/dev/null 2>&1"
    expect_exit: 0
---

# 测试先行：红 → 绿 → 重构

先写测试（**红**）→ 让 AI 实现到**绿** → 重构。

先测试后代码，天然约束 AI 不乱来——它的目标从"看起来像对的"变成"让这几条断言通过"。

**练习**：挑一个练习 Issue，先用 pytest 写 3 个失败断言，再放 AI 实现到全绿。

```bash
python3 -m pytest -q      # 先看到红
# ...让 AI 实现...
python3 -m pytest -q      # 必须全绿
```
