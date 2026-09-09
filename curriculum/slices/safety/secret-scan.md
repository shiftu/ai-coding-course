---
id: safety/secret-scan
dimension: safety-gate
level_edge: S1
type: exercise
env: own-mac
---

# 扫一遍仓库有没有密钥泄漏

```bash
git log -S "ak_" --oneline
git log -S "sk-" --oneline
grep -rn "sk-[A-Za-z0-9]\{16,\}" .
```

**练习**：扫描 playground（讲师预埋了 1 处），然后把密钥全量迁进
`~/.hermes/.env`（权限 600），删除仓库里任何明文凭据。

> 本切片**不设机验**：扫描是针对学员自己的仓库，而课程仓库里本来就存放着
> 测评任务故意预埋的假密钥。把它当内容保鲜检查会永远误报。
