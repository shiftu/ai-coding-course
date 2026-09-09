---
id: tool/env-setup
dimension: 工具操作
level_edge: L0->L1
type: exercise
env: own-mac
verify:
  - cmd: "claude --version && codex --version && hermes --version && lark-cli --version"
    expect_exit: 0
---

# 把武器领了：四件工具装上并跑出版本号

装齐四件工具，每条命令都要能打出版本号。

```bash
npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex
npm install -g @larksuite/cli
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
hermes doctor        # 全绿才算通过
```

**验收**：`claude --version`、`codex --version`、`hermes --version`、`lark-cli --version`
四条命令全部有输出、无 error。

版本号打不出来，九成是 npm 全局目录不在 PATH。这种问题报给讲师五秒解决，别自己折腾半小时。
