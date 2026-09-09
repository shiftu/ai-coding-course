# Spike 结论 · v1.1 可行性验证

> 日期：2026-08-20 · 目标：回答"投不投"，不是交付代码
> 所有构建产物均为**一次性**，清理方式见文末

## 判定：地基成立，可以投 —— 但 v1.1 有 3 处必须改

核心假设全部验证通过：arm64 工具链可用、内部网关闭环可用、证据链存在且可机读、Mac mini 扛得住目标并发。
没有发现任何"推倒重来"级的阻断项。

---

## 一、已验证（附证据）

| # | 验证项 | 结果 | 证据 |
|---|---|---|---|
| 1 | linux/arm64 工具链 | ✅ 全部**实际可执行** | claude-code 2.1.237 · codex 0.148.0 · lark-cli 1.0.88 · ttyd 1.7.7 · asciinema 2.2.0 · node 26.7.0，`uname -m`=aarch64 |
| 2 | 沙盒镜像体积 | ✅ 1.47 GB | 单层 `node:26-bookworm-slim` + 5 工具 |
| 3 | **只经内部网关跑通** | ✅ 最重要的一条 | 容器内 claude-code 无任何 Anthropic 登录，仅靠 `ANTHROPIC_BASE_URL` 指向网关，真实修复了 `a-b`→`a+b` 的 bug，git diff 有痕 |
| 4 | 网关双协议 | ✅ | `/v1/messages`（claude-code）与 `/v1/chat/completions`（codex）均 200 |
| 5 | 容器→宿主连通 | ✅ **不需改绑 0.0.0.0** | 容器经 `192.168.5.2`(=host.lima.internal) 直达宿主 127.0.0.1：gateway 200、Gitea 200 |
| 6 | 证据链存在 | ✅ | claude-code transcript / asciinema v2 / git 状态 / 网关 request_logs 四样齐全 |
| 7 | 隐私：网关不存 prompt 正文 | ✅ | `request_logs.prompt_excerpt` 实测为空 |
| 8 | 5 人并发 | ✅ 无压力 | 5 个并发 claude-code 会话 exit=0 全部成功；VM 1836MB / 5910MB；活跃会话约 158MB/个 |
| 9 | **hermes 在 arm64 实跑** | ✅ **已实测**（原为推断） | 本地构建成功，容器内 `hermes --version` → v0.20.1 / Python 3.13.5 / node 26.5.1，镜像 4.07GB |
| 10 | **四件工具同镜像共存** | ✅ 已实测 | 单一 arm64 镜像 4.95GB：claude 2.1.237 · codex 0.148.0 · lark-cli 1.0.88 · hermes v0.20.1 · ttyd 1.7.7 · asciinema 2.4.0，全部可执行 |
| 11 | **ttyd 内 TUI 体验** | ✅ 人工确认通过 | Esc 中断 / Ctrl+O 展开思考 / 复制粘贴 / 刷新后会话保持 —— 四项均正常。测评页内嵌 web 终端方案成立，无需退回 SSH |

## 二、必须修改 v1.1 的 3 处

### ① §4.3 信号采集：`shell 历史` 这条不成立，换成 agent transcript

实测容器内 `~/.bash_history` **文件根本不存在**——非交互 shell 不写，交互 shell 也只在干净退出时 flush。
但发现了更好的东西，v1.1 完全没提到：

**`~/.claude/projects/<slug>/<uuid>.jsonl`** —— claude-code 的结构化会话记录。本次测试里它包含
`Read ×2 / Edit ×1 / Bash ×1` 的 tool_use 事件，**可以直接对着 rubric 逐条机器判定**：

- "先读后改" → transcript 里 Read 是否在 Edit 之前
- "提交前跑过测试" → 是否存在含 `pytest` 的 Bash 事件
- "范围控制" → 工具调用总数与文件触及面

这比 shell 历史强一个数量级，且天然存在、无需埋点。**批改 agent 应以它为主证据源。**

### ② §1.1 工程面漏了一件：每学员一把网关 API key

`request_logs` 有 `api_key_id` / `team_id` 字段，但用 admin token 调用时**两者都是 NULL**——
即无法归属到人。必须给每个学员签发独立 key（`llm-gateway init --team=<slug>`，现有 20 行 api_keys 证明机制可用）。
这带来一条 v1.1 没算的运维职责：**key 的签发、轮换、毕业回收**，且它正是 §8「毕业即停止采集」的执行开关。

### ③ hermes 不是 npm 包，且没有预构建镜像

hermes 是 **Python**（uv venv，非 npm）。它自带官方多架构 Dockerfile（有显式 aarch64 分支），
但 CI **只构建 `:test`，不发布到任何 registry**，所以容器里要 hermes 只能本地构建。
Dockerfile 注释显示 arm64 上仅一个 chmod pass 就 222 秒，整体 **15–45 分钟**。

**实测补充（2026-08-20）**：本地构建成功，需要 **buildx**（Dockerfile 用了 `COPY --chmod`，
legacy builder 会在第 21 步失败）。首次冷构建按分钟级计，**有 BuildKit 缓存后重建仅 33 秒**——
所以"15–45 分钟"只是首次成本，日常迭代不痛。

→ 沙盒镜像最终形态：**以 hermes 镜像为基底**，叠加 claude-code / codex / lark-cli / ttyd /
asciinema，单一镜像 4.95GB，六件工具全部可执行（已实测）。不需要拆两层——hermes 基底已自带
node 26 + python + uv + git + ripgrep + ffmpeg，正好是沙盒需要的东西。

### ④ 沙盒必须跑在不拦 Bash 的权限模式下（§6 硬要求）

写 rubric 时用真实工件验出来的。会话记录里 `is_error: true` 有两种成因：命令真的失败，
或者**命令被权限系统拦下从未执行**（`This Bash command contains multiple operations.
The following part requires approval: ...`）。两者信号完全相同。

实测 `--permission-mode acceptEdits` 下，`python3 -m pytest x.py -q | tail -30` 这类
复合命令会被判定需要审批而拦截。后果有两层：

- **学员寸步难行**——沙盒里最常用的命令形态被挡；
- **证据链被污染**——被拦的学员在批改时会呈现为"从未运行过任何测试"，判分完全失真。

→ 测评沙盒的 claude-code 必须预先配好 Bash 放行（allowlist 或等效权限模式）。
这条在 v1.1 里完全没提，但它同时影响可用性和判分正确性。

### ⑤ 宿主机要装 buildx，且需要 registry mirror / 重试（运维前置）

两条都在实测里踩到：

- **buildx 必装**：hermes 的 Dockerfile 用了 `COPY --chmod`，该语法**要求 BuildKit**。
  colima 默认的 docker 走 legacy builder，构建到第 21 步直接失败；
  加 `DOCKER_BUILDKIT=1` 后报 "buildx component is missing"。宿主机 provisioning
  脚本里必须包含 buildx 安装。
  *本机已装*：`brew install docker-buildx` + 在 `~/.docker/config.json` 加
  `cliPluginsExtraDirs: ["/opt/homebrew/lib/docker/cli-plugins"]`（v0.36.1，已验证）。
- **registry 抖动**：

hermes 镜像构建第一次挂在 colima VM 内 DNS 解析
  `registry-1.docker.io` 超时，重试即恢复。单次抖动可接受，但开营当天镜像拉不动
  是运营事故——建议本地 mirror。

## 三、未验证 / 待确认

> ttyd TUI 体验、hermes arm64 实跑、四件工具同镜像共存均已于 2026-08-20 验证完成（上表 9–11 项）。
> **spike 的三个问题全部闭环，无剩余阻断风险。** 下表只剩一条运营注意事项。

| 项 | 状态 |
|---|---|
| 网关模型名前缀 | ⚠️ 必须带 `charaboard/`；模型名写错时网关返回 **404 而非 400**，错误面误导，需在 D0 文档里明确 |

## 四、清理（一次性产物）

```bash
docker rm -f spike-tty
docker rmi spike-sandbox:throwaway spike-combined:throwaway hermes-spike:arm64
colima stop            # 若不再需要
```

Dockerfile 与构建日志在 scratchpad：`.../scratchpad/spike/`
