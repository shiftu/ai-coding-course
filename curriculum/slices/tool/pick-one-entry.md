---
id: tool/pick-one-entry
dimension: 工具操作
level_edge: L0->L1
type: pitfall
env: container
---

# 别同时开三个入口做同一件事

入门期先选**一个**主入口，推荐 CLI —— 可读性强、能看日志、出问题好排查。

三个入口同时开着做同一件事，你会分不清是哪个改了文件、哪个的上下文是对的。
