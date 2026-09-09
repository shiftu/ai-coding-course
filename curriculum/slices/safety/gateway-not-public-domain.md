---
id: safety/gateway-not-public-domain
dimension: safety-gate
level_edge: S1
type: pitfall
env: own-mac
---

# 别用公网域名直连网关

用 `llm.jiangtao.lol` 这类公网域名直连，会被 Cloudflare WAF 拦下：
`403 Your request was blocked`。

**一律走 `127.0.0.1:7421`。** 这不只是能不能通的问题——走公网意味着流量出了内网边界。
