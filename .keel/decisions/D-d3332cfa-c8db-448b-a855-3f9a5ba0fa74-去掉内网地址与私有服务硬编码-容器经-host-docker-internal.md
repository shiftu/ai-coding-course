---
schema: 1
id: D-d3332cfa-c8db-448b-a855-3f9a5ba0fa74
title: 去掉内网地址与私有服务硬编码：容器经 host.docker.internal 到网关，外部依赖全部可配可换
status: accepted
date: "2026-09-13"
by: agent:claude
tags:
  - sandbox
  - ops
  - open-source
scope:
  - platform/control/sandbox.py
  - platform/control/gateway.py
  - platform/control/e2e.py
  - platform/control/simulate.py
  - platform/sandbox/smoke.sh
  - platform/sandbox/rootfs/etc/profile.d/10-microclass.sh
  - platform/sandbox/rootfs/usr/local/bin/microclass-config
  - curriculum/rubric/judge.py
  - README.md
  - platform/sandbox/README.md
supersedes: []
superseded_by: []
rule_migration: []
confidence: null
review_after: "2026-12-12"
evidence:
  - E-274c87cf-0498-4dda-8f03-35bb9b2c7c6d
  - E-ffc742cb-01a4-43ee-9134-d56d576ed5d7
  - E-1a5704f7-b206-40a4-bf3c-24900bf67547
---

## 背景

仓库要开源给外部开发者跑。此前平台代码写死了参考部署的环境：容器看网关的地址是 colima 的
固定 IP `192.168.5.2`（sandbox.py / smoke.sh），仿真器写死 `/Users/panda/...` 绝对路径，
e2e / smoke 写死只在某个网关上存在的模型别名 `charaboard/claude-sonnet-5`，课程文案里有
`llm.jiangtao.lol`、`gitea.jiangtao.lol`、`ai-workshop` 这类私有域名和组织名。
外部开发者拿到仓库无法确定哪些是必需依赖、哪些只是文案，也没有一处配置能把它指向自己的环境。

## 决定

1. 容器看网关的地址默认 `host.docker.internal`，`docker run` 时加 `--add-host host.docker.internal:host-gateway`
   兜底（仅在走默认别名时加）。`MICROCLASS_GATEWAY_HOST` / `MICROCLASS_GATEWAY_PORT` 可覆盖。
   smoke.sh 用同样的默认和同样的 add-host。
2. 网关 admin token 路径 `MICROCLASS_GATEWAY_TOKEN_FILE` 可配（gateway.py 与 judge.py 认同一个变量）。
3. e2e / smoke 的探测模型取 `versions.lock` 的 `MODEL`（smoke 另有 `MICROCLASS_SMOKE_MODEL`），
   不再另写别名；仿真器路径改为从 `sandbox._CURRICULUM` 派生。
4. 文案层：私有域名换 `llm.example.com` 一类占位，组织名标注为示例；README 新增「外部依赖」表
   （llm-gateway 必需，hermes-agent 基底必需，飞书 / Gitea 可选）和环境变量表；
   hermes 基底改为从上游 NousResearch/hermes-agent 仓库构建，不再引用本机 `~/.hermes/hermes-agent`。
5. 历史文档（docs/design、spike）保留原文，那是当时的记录，不是当前配置。

## 备选与理由

- 继续写死 IP，只在 README 说明：外部开发者在 Docker Desktop / Linux 上第一步就断，否决。
- 用 `--network host`：容器直接看宿主回环，但 ttyd 端口只绑回环的隔离设计随之失效，否决。
- 在 sandctl create 时探测 docker 运行时再选 IP：多一层猜测，而 `host-gateway` 是 docker 20.10+
  的标准做法，VM 型运行时下它和天然解析结果一致（colima 实测都是 192.168.5.2），无需探测。
- 把模型别名也做成环境变量：`versions.lock` 已是唯一真源，再加一处会破坏单一真源约定，否决。

## 后果与验证方式

- 后果：rootfs 两个脚本改了文案，镜像戳会变，`./build.sh` 后 smoke 的「镜像身份」项才会绿；
  参考部署（colima）行为不变，实测 `host.docker.internal` 与 `--add-host …:host-gateway` 都解析到 192.168.5.2。
  Linux 原生 docker 下网关必须监听 0.0.0.0 或 docker0，README 已写明。
- 验证：`platform/control/test_redact.py` 等离线测试全绿；`git grep` 不再命中私有域名 / 本机路径；
  `docker run --add-host host.docker.internal:host-gateway alpine wget http://host.docker.internal:7421/healthz` 返回 ok。
