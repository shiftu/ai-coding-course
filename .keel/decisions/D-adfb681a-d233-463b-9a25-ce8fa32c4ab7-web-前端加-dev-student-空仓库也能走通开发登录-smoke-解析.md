---
schema: 1
id: D-adfb681a-d233-463b-9a25-ce8fa32c4ab7
title: web 前端加 --dev-student：空仓库也能走通开发登录；smoke 解析取最后一行 JSON
status: accepted
date: "2026-09-13"
by: agent:claude
tags:
  - web
  - dx
  - sandbox
scope:
  - platform/web/serve.py
  - platform/web/test_web.py
  - platform/web/README.md
  - platform/control/sandctl
  - platform/sandbox/smoke.sh
  - README.md
supersedes: []
superseded_by: []
rule_migration: []
confidence: null
review_after: "2026-12-12"
evidence:
  - E-4f8b3d69-5675-4011-9a40-9179c75fffa6
  - E-53119341-b832-4611-a13c-ca11eddf0355
---

## 背景

2026-09-14 把全部学员销号后按 README 从零跑一遍，两处对不上：
1. 「快速开始」写的是 `--dev-login` 后"填任意学员 ID 就能进"，实际开发登录只认档案里有的学员
   （`_dev_login` 查 `store.exists`，test_web 也断言陌生 ID 被拒）。空仓库登录页把所有 ID 都拒掉，
   外部开发者第一步就断。
2. smoke.sh 第 6 项把 claude-code 输出里第一个 `{` 当结果 JSON。统一模型换成网关别名后，
   claude-code 会先打一行 `[claude-code:unrecognized_model] {…}` 警告，解析拿到的是警告，
   一次成功的请求被判成失败。

## 决定

1. `serve.py --dev-student <ID>`（可重复，只配合 `--dev-login`）：档案不存在就写一份只有档案的记录
   （`dev_seed: true`，无容器、无 key、`collecting: false`）。**不放开**开发登录的存在性检查。
2. `sandctl list / url / destroy` 认得 `dev_seed` 档案：list 显示「无(开发)」，url 明确报错并指路，
   destroy 只删档案。
3. smoke.sh 取**最后一行**以 `{` 开头的 JSON 作为结果。
4. README「快速开始」改用 `--dev-student stu-dev`；「完整安装」加"零、先确认网关在"和一条实测过的完整链路。

## 备选与理由

- 开发登录自动建档案：任何人填个 ID 就能造学员，破坏「不做自助开通」的边界，否决。
- 加一个 `sandctl add --no-sandbox`：把"只有档案的学员"做成正式概念，会牵动 harvest / capacity /
  image-audit 的语义，为一个开发入口不值得；放在 serve.py 的开发开关下，边界清楚。
- smoke 用 `--output-format json` 之外的方式取结果：没有更稳的接口，最后一行 JSON 是 claude-code 的稳定契约。

## 后果与验证方式

- `python3 platform/web/test_web.py` 覆盖 seed 幂等、无 key、能登录、三页 200、非法 ID 被拒。
- 实测链路：destroy 全部学员 → validate → serve --dev-login --dev-student → build → smoke 8/8 →
  sandctl create stu-a（doctor 全通）→ list/info/url/capacity/image-audit → harvest + grade → graduate → destroy。
