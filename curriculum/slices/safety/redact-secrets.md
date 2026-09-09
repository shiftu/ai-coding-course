---
id: safety/redact-secrets
dimension: safety-gate
level_edge: S1
type: exercise
env: own-mac
---

# 打开输出自动打码

```bash
hermes config set security.redact_secrets true
```

开了之后 agent 的输出里密钥会自动打码。**这是兜底，不是替代品** ——
你依然不该把密钥放进它能读到的地方。
