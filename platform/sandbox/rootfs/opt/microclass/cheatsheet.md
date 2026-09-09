# 速查卡

> 这张卡只列**命令怎么写**。记不住命令不扣分 —— 随时 `card` 打开它。
> 卡上不会告诉你该做什么，那是你的判断。

## claude-code

| 想干什么 | 敲什么 |
|---|---|
| 进交互 | `claude` |
| 一次性提问，不进 TUI | `claude -p "……"` |
| 清空上下文重开 | 交互里 `/clear` |
| 恢复上一次会话 | `claude --continue` |
| 挑一个历史会话恢复 | `claude --resume` |
| 中断它正在做的事 | `Esc` |
| 展开/收起思考过程 | `Ctrl+O` |
| 看版本 | `claude --version` |

## codex

| 想干什么 | 敲什么 |
|---|---|
| 进交互 | `codex` |
| 一次性执行 | `codex exec "……"` |
| 只读模式 | `codex exec "……" -s read-only` |
| 看版本 | `codex --version` |

> codex 用的模型和另外三件工具不一样（`codex --version` 旁边看不到，
> 想确认就 `grep ^model ~/.codex/config.toml`）。原因是统一模型在 codex 上跑不正常。
>
> codex 每次启动会说一句 `Model metadata for … not found`。**这是正常的，不用管。**
> 它认不出我们网关上的模型名，于是拿一套保守的默认参数去估上下文长度 ——
> 请求本身照常发得出去、回得来。

## hermes

| 想干什么 | 敲什么 |
|---|---|
| 进交互 | `hermes` |
| 接着上次 | `hermes --continue` |
| 看有哪些 skill | `hermes skill list` |
| 看定时任务 | `hermes cron list` |
| 看版本 | `hermes --version` |

## lark-cli

| 想干什么 | 敲什么 |
|---|---|
| 体检（配置对不对） | `lark-cli doctor` |
| 看版本 | `lark-cli --version` |

## git

| 想干什么 | 敲什么 |
|---|---|
| 看改了什么 | `git diff` |
| 看已暂存的改动 | `git diff --staged` |
| 看状态 | `git status` |
| 看最近提交 | `git log --oneline -10` |
| 撤销工作区改动 | `git restore <file>` |
| 建分支并切过去 | `git switch -c <name>` |
| 提交 | `git commit -am "……"` |

## 跑测试

| 语言 | 敲什么 |
|---|---|
| Python | `pytest -q` / `pytest -q path/to/test_x.py` |
| Python（只跑一个用例） | `pytest -q -k 名字片段` |
| Node | `npm test` |
| Go | `go test ./...` |

## 网关

本沙盒的 AI 请求全部经内部网关，环境变量已配好，**不需要你填任何 key**：

```
ANTHROPIC_BASE_URL   # claude-code 走这里
OPENAI_BASE_URL      # codex 走这里
```

看网关活着没：`curl -s $MICROCLASS_GATEWAY/healthz`

## 别的

| 想干什么 | 敲什么 |
|---|---|
| 再打开这张卡 | `card` |
| 全文搜索 | `rg 关键词` |
| 按文件名找 | `fd 名字` 或 `find . -name '*.py'` |
