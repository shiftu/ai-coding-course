---
id: quality/read-diff
dimension: 质量验证
level_edge: L1->L2
type: exercise
env: container
---

# 用 git diff 通读一遍改动

```bash
git diff
```

重点看两样：

- **有没有删掉无关代码** —— AI 重构时容易顺手删掉它认为没用的东西
- **有没有引入魔法常量** —— 硬编码的数字和字符串

跑得起来 ≠ 改对了。
