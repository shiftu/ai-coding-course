---
id: tool/gateway-connect
dimension: 工具操作
level_edge: L0->L1
type: exercise
env: own-mac
verify:
  - cmd: curl -sf -o /dev/null http://127.0.0.1:7421/healthz
    expect_exit: 0
---

# 把所有工具指向内部网关

公司所有 AI 调用都从 llm-gateway 出去，这是"水电"。先确认它通：

```bash
curl -s http://127.0.0.1:7421/v1/models -H "Authorization: Bearer $LLM_GW_KEY" | head -5
```

见到模型列表即通。然后把两个 CLI 指过去：

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:7421/v1
export OPENAI_BASE_URL=http://127.0.0.1:7421/v1
```

Key 用 llm-gateway 发的 `ak_xxx`，不是模型厂商的 key。

> 本切片的机验只探 `/healthz`（无需鉴权）—— 它验的是"网关端点还在、还响应"，
> 属于内容保鲜。带个人 key 的鉴权检查不能进机验：哨兵没有学员的 key，
> 那样每次都会红，Issue 很快就没人看了。
