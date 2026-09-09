---
id: safety/key-rotation
dimension: safety-gate
level_edge: S1
type: pitfall
env: own-mac
---

# 密钥进了 git 历史，删文件不够

要 **rotation + 清洗历史**。

删掉文件只是让当前 HEAD 干净了，历史里还在，而且已经躺在每个 clone 过的人机器上。
**先轮换密钥**（让泄漏的那把失效），再考虑清洗历史。
