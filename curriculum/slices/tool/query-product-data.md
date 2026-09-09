---
id: tool/query-product-data
dimension: 工具操作
level_edge: L1->L2
type: exercise
env: own-mac
---

# 用自然语言查产品数据，不写 SQL

```bash
hermes -s posthog-analysis chat -q "昨天 DAU 多少？新老用户各多少？"
```

**练习**：查 3 个指标——昨日 DAU、日新增、付费转化，并用演示里的口径核对数字是否一致。

交付物：一个查询结论 + 一张图 + **口径说明**（为什么是这个数）。
