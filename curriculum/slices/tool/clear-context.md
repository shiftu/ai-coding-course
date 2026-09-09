---
id: tool/clear-context
dimension: 工具操作
level_edge: L1->L2
type: exercise
env: container
---

# /clear 与 checkpoint：控制上下文和退路

- **改需求时先 `/clear`**，或明确说"忽略上一条"。否则它会把新旧需求缝在一起，
  产出一个你没要过的东西。
- **每阶段开新上下文**，不要在一个会话里从头做到尾。
- **`git commit` 就是人类最好的 checkpoint** —— 比任何工具的回滚都可靠。
