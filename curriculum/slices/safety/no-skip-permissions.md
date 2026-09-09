---
id: safety/no-skip-permissions
dimension: safety-gate
level_edge: S1
type: pitfall
env: container
---

# 全权限模式新手禁用

`--dangerously-skip-permissions` 这类全权限开关，**新手期禁用**。

先学会审——你要能看懂它想执行什么、为什么，再决定要不要省掉这一步。
跳过审核省下的几秒，抵不过一次 `rm -rf` 的代价。
