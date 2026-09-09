---
id: safety/key-storage
dimension: safety-gate
level_edge: S1
type: pitfall
env: own-mac
---

# 密钥存哪里：.env 或 Keychain，永远不进仓库

Key 放 `~/.hermes/.env`（权限 600）或 macOS Keychain。**严禁 commit 进仓库。**

密钥一旦进了 git 历史，删文件是不够的——要 **rotation + 清洗历史**。删掉的文件还躺在
每个 clone 过这个仓库的人机器上。

自查：

```bash
git log -S "sk-" --oneline
git log -S "ak_" --oneline
grep -rn "sk-[A-Za-z0-9]\{16,\}" .
```
