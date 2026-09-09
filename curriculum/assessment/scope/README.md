# 各任务变体的「范围控制」判定素材

`judge.py` 判 `spec/scope-control` 时要知道**这一份任务埋了哪两处歧义、超量多少**。
这些内容原先写死在 `judge.py` 的 PROMPT 里，任务 A 专用 —— 拿它去判轨道 B 的学员，
会得到一份**看起来合法、实际全错**的判定。那比报错更糟。

## 为什么放在这里，不放在 `task-X/` 里

`task-X/` 会被**整个复制进学员容器**（见 `platform/control/sandbox.py` 的 `seed_task`）。
把歧义清单放进去，等于连同答案一起发下去 —— 埋点在复盘时揭开，不是在测评时。
这个目录是 `task-X/` 的兄弟，不会被复制。

## 字段

| 字段 | 用途 |
|---|---|
| `task` | 变体 id，和 `task-<id>/` 的后缀一致 |
| `repo` | 仓库名，只用于人看 |
| `ambiguities[].issue_line` | 渲染进 prompt 的「任务埋了什么」那一行 |
| `ambiguities[].criterion` | 渲染进 prompt 的判据条目 |
| `overload_line` | 超量那一行 |

改这里 = 改判定。改完跑 `python3 judge.py --render a | diff - <基线>` 确认没动到别的变体。
