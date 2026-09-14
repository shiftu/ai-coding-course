---
id: safety/gateway-not-public-domain
dimension: safety-gate
level_edge: S1
type: pitfall
env: own-mac
---

# 别用公网域名直连网关

用 `llm.example.com` 这类公网域名直连网关，很可能被边界上的 WAF 拦下
（典型症状：`403 Your request was blocked`）。

**一律走本机地址 `127.0.0.1:7421`**（端口以运维给的为准）。这不只是能不能通的问题——
走公网意味着流量出了内网边界。
