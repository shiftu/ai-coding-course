---
id: tool/toolchain-map
dimension: 工具操作
level_edge: L0->L1
type: demo
env: container
---

# 全景图：一个网关、三个入口、一套数据、一个中枢

建立全局心智，别一上来就陷进某个工具的参数里。

- **llm-gateway**（`127.0.0.1:7421`）—— 统一模型出口，所有入口同源
- **三个入口** —— CLI 结对（Claude Code / Codex）、Hermes 数字员工、飞书机器人
- **一套数据平台** —— PostHog（产品）/ Prometheus（成本资源）/ SigNoz（链路）
- **一个协作中枢** —— Gitea（仓库、Issue、Milestone）

关键认知：三个入口只是**同一个模型能力的不同交互形态**，不是三种不同的 AI。
