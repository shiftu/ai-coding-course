---
schema: 1
id: D-9c311993-66fe-4238-aa0a-e9618105af3b
title: 学员容器加内存/进程数硬上限，sandctl capacity 按宿主机实测算容量
status: accepted
date: "2026-09-10"
by: agent:claude
tags:
  - sandbox
  - capacity
  - ops
scope:
  - platform/control/sandbox.py
  - platform/control/capacity.py
  - platform/control/test_capacity.py
  - platform/control/sandctl
  - platform/control/README.md
supersedes: []
superseded_by: []
rule_migration: []
confidence: null
review_after: "2026-12-09"
evidence:
  - E-6c1e57a8-4ed6-4e8f-8add-63ae5c116578
  - E-16f39d28-9ad0-4a50-a29c-754fb424c2f6
  - E-6663e4f6-8349-404d-9b35-3d9a23f6461a
---

## 背景

设计文档写「64G 宿主机撑 30 并发」，没有量化依据。docker run 没设任何资源上限，
平台不知道一个学生占多少，一个跑飞的进程能把整台宿主机拖垮。
2026-09-10 实测：活跃沙盒（claude + hermes 同时跑）约 950 MiB / 145 进程，空闲约 20 MiB。

## 决定

1. 每个学员容器 `--memory 2g --memory-swap 2g --pids-limit 512`（sandbox.MEM_LIMIT / PIDS_LIMIT，
   resource_limit_args() 是 docker run 和 docker update 的唯一来源）。swap 等于 memory，上限才是硬的。
2. 新增 `sandctl capacity`：从 docker info / stats / system df 取数，给两条线：
   硬上限 = (总内存 − 预留) / MEM_LIMIT；实测余量 = (总内存 − 预留 − 已用) / 活跃均值。
   `--apply-limits` 用 docker update 给老容器补上限，即时生效不重启。
3. 预留 = min(4 GiB, 总内存/4)，开发机不至于算出 0 人。

## 备选与理由

- 不设上限、只报平均数：容量只是统计值，单个失控进程仍能拖垮全机，放弃。
- 用 cgroup 直接读：docker stats 已经给出同样的数且跨 colima/Linux 一致，不另起炉灶。
- CPU 上限：agent 主要在等 LLM 响应，实测活跃容器 <5%，不设；瓶颈在网关而非宿主机。

## 后果与验证方式

- 已开的容器不自动带上限，要跑一次 `sandctl capacity --apply-limits`（本次已对 3 个在跑容器执行，
  docker inspect 与容器内 cgroup memory.max / pids.max 均确认 2 GiB / 512）。
- 离线验证：`python3 platform/control/test_capacity.py`（解析、算术、渲染、limit 参数）。
- 在线验证：`python3 platform/control/sandctl capacity` 无「没有内存上限」告警。
