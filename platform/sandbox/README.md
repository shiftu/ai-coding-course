# 学员沙盒镜像

一个镜像，六件工具，linux/arm64。`microclass/sandbox:current` 是所有学员的运行环境。

```
./build.sh          # 读 versions.lock 构建
./stamp.sh          # 只算构建戳，不构建
./smoke.sh          # 冒烟（端到端那项要 MICROCLASS_SMOKE_KEY）
```

## 镜像身份：tag 是名字，image id 才是身份

`build.sh` 打的 tag 是 `./stamp.sh` 算出来的 12 位构建戳，
戳 = **`versions.lock` + `Dockerfile` + 整个 `rootfs`** 的哈希。

这里踩过一次，而且是在生产上踩的。原来的戳只哈希 `versions.lock`：

```
改一行 rootfs/usr/local/bin/card  →  重建  →  内容不同、tag 一模一样的镜像
```

同名 tag 被挪到新镜像上，旧镜像变成无名氏。学员档案里那行
`image: microclass/sandbox:cad5bf89ed2b` 于是同时"属于"两个不同的环境，
「回溯这人当时用的是哪套环境」当场落空 —— 实测 `stu-jt` 和 `stu-p`
档案里记着同一个 tag，容器实际跑的却是两个不同的镜像，而那两个镜像都已经不在本地了。

三件事一起做才堵得住：

| 记什么 | 是什么 | 为什么不够 / 为什么需要 |
|---|---|---|
| `image` | 带戳的 tag | 只是宿主机上的一个标签，`docker tag` 一句话就能让它指向别处 |
| `image_id` | docker 算的内容 sha256 | **真正的身份**，改不了也不会重名。档案和 manifest 以它为准 |
| `image_stamp` | 构建戳 | 可读的对照：拿着它能回到当时那份 lock + Dockerfile + rootfs |

戳同时烙进镜像的 `LABEL org.microclass.image-stamp` 和容器里的
`$MICROCLASS_IMAGE_STAMP` —— tag 全被删光、只剩一个还在跑的容器时，它自己也答得出来。

**戳是输入寻址，不是内容寻址。** 同样的输入不保证产出同样的镜像（apt/npm 上游会漂）。
`build.sh` 发现同一个戳这次产出了不同的 image id 会明确打出来，不掩盖。

核对与补记（在 `platform/control/`）：

```bash
python3 sandctl image-audit          # 只读：档案记的 vs 容器实际在跑的
python3 sandctl image-audit --fix    # 以容器为准，补 image_id / image_stamp
```

## 基底怎么来的

基底是 `versions.lock` 里 `HERMES_BASE` 指的那个 tag，用上游
[hermes-agent](https://github.com/NousResearch/hermes-agent) 仓库**自带的**多架构 Dockerfile
构建（它有显式 aarch64 分支）。本仓库不含这份源码，也不发布这个镜像，自己构建一次即可：

```bash
BASE=$(sed -n 's/^HERMES_BASE=//p' versions.lock)       # 例如 microclass/hermes-base:v2026.9.7
git clone https://github.com/NousResearch/hermes-agent /tmp/hermes-agent
cd /tmp/hermes-agent
git checkout <和 tag 对应的上游版本>                       # 版本号跟着 HERMES_BASE 的后缀走
DOCKER_BUILDKIT=1 docker build -t "$BASE" .
```

要点：

- **必须有 buildx**。hermes 的 Dockerfile 用了 `COPY --chmod`，该语法要求 BuildKit。
  没有会在第 21 步报 `the --chmod option requires BuildKit`。
  装：`brew install docker-buildx`，再把 `cliPluginsExtraDirs` 合进 `~/.docker/config.json`。
- arm64 上首次构建 15–45 分钟（Dockerfile 注释说光一个 chmod pass 就 222 秒）。
  有 BuildKit 缓存后重建约 33 秒。
- 需要能拉 registry。实测遇到过 `registry-1.docker.io` DNS 超时，重试即可；
  长期建议配 registry 镜像 + 重试。

选它当基底是因为它已经带了 node / uv / git / ripgrep / ffmpeg，
叠上四件工具后单镜像约 5GB，不需要拆多层。

## 四条硬要求（都是踩出来的，不是想出来的）

### 1. claude-code 不能拦 Bash

`/etc/claude-code/managed-settings.json` 里把 Bash 放进 `permissions.allow`。

**为什么**：权限弹窗在非交互模式下等于自动拒绝，会在会话记录里留下

```json
{"is_error": true, "content": "This command requires approval"}
```

于是"从没跑过测试"和"跑测试被拦下"在证据里长得一模一样，
整条证据链被毒化，批改 agent 判什么都是错的。

A/B 实测（同一条命令、同一个镜像）：

| 配置 | `permission_denials` | 结果 |
|---|---|---|
| 无 managed-settings | `[{"tool_name":"Bash",...}]` | `is_error: true`，"需要你批准" |
| 有 managed-settings | `[]` | `is_error: false`，算出 42 |

放开权限不是偷懒 —— **隔离边界是容器本身**（设计文档 §6），
不是权限弹窗。弹窗在这里只制造假证据。

### 2 + 3. 练习依赖要装进「学员真正调用的那个 python」

基底把 `/opt/hermes/.venv/bin` 放在 `ENV PATH` 最前，所以镜像里 `python3` 是 venv 那个，
`pip3 install` 装进 `/usr/bin/python3` 的包学员看不见。用：

```dockerfile
uv pip install --python /opt/hermes/.venv/bin/python3 "pytest==${PYTEST_VERSION}"
```

**但这还不够。** `/etc/profile` 会**重置 PATH**，把 ENV 里的顺序冲掉 ——
构建期 `RUN`（非登录 shell）看不到这个差异，会给出假绿；
而学员从 ttyd 进来的是**登录 shell**，`python3` 落到 `/usr/bin/python3`，
`python3 -m pytest` 直接 ModuleNotFoundError。

所以 `/etc/profile.d/10-microclass.sh` 里把 venv 路径重新前置，
并且**自检一律用 `bash -lc` 跑**：学员敲的是哪个 shell 就验哪个。

（这条是 smoke.sh 第一次运行抓出来的 —— 构建期自检当时是绿的。）

### 4. hermes 必须在 PATH 上

二进制在 `/opt/hermes/bin/hermes`，但 `command -v hermes` 找不到。
`ln -sf` 到 `/usr/local/bin/hermes`，课程里 4 条 hermes 机验才会绿。

### 5. git 必须认预置进来的仓库

`/etc/gitconfig` 里 `safe.directory = *`。

平台会把测评任务仓库预置进 `/workspace`（docker cp / bind mount / 解压），
这些方式带进来的属主未必是容器里的用户，git 直接罢工：

```
fatal: detected dubious ownership in repository at '/workspace/task-a'
```

后果不是「学员看到一条报错」，而是**证据源 ② git 状态整条哑掉** ——
批改时看起来就像这人一个仓库都没碰过。沙盒是一人一容器的隔离环境，
这里放开没有实际风险。放 `/etc/gitconfig` 而不是 `~/.gitconfig`：
沙盒里 `HOME=/workspace` 是持久卷，家目录里的配置不随镜像走。

## 单版本策略

## 自检 ≠ 体检

两件事，别混：

| | `microclass-selfcheck` | `microclass-doctor` |
|---|---|---|
| 查什么 | 版本号、PATH、配置文件在不在 | **每件工具真的发一次请求** |
| 什么时候 | 构建期 + 交付前 | 交付前（`sandctl create` 自动跑）、学员随时 |
| 需要网关吗 | 不 | 需要，还要学员自己的 key |

**为什么要分开**：自检在构建期跑，那时既没网关也没学员 key，测不了「能不能用」。
结果就是 codex 和 hermes 两件工具坏着、自检一路绿灯，一直发到学员手里才被发现。
**装上了 ≠ 跑得通。** 交付闸现在卡在 doctor 上：必修项失败 → `sandctl create` 直接拒绝交付。

体检把失败分两档：
- **FAIL（必修）** —— 退出 1，容器不交付。
- **已知待修** —— 退出 0，但明确打出来，不藏。目前只有 codex（见下）。

## 交付物也要体检，不只是工具

体检最初只查四件工具。结果是**工具全绿，学员少东西** —— `card` 和
`/workspace/task-a` 双双缺失，`sandctl create` 一路打印"体检全通过"。

两个 bug 成因完全不同，但漏出去的原因是同一个：**检查的是我们装了什么，
不是学员拿到了什么。**

### bug 1：`card` 在测评模式下消失

`card` 原本是 `/etc/profile.d/10-microclass.sh` 里的一个 **shell 函数**。
测评模式下 profile.d 的最后一步是 `exec microclass-record`，而录屏起的是
`$SHELL -i` —— **交互，但非登录**。非登录 shell 不读 `/etc/profile`，
函数就此消失。学员在录屏里敲 `card` 得到 command not found，而 banner
还在告诉他"忘了命令就敲 card"。

为什么拖到现在才发现：课程模式默认不录屏（`sandctl create --record` 才录），
`card` 一直是好的；只有测评模式坏。
为什么工具没跟着坏：它们在 PATH 上，而 PATH 来自 Docker ENV ——
非登录 shell 反而**不会**被 `/etc/profile` 重置。

两处修：

1. `card` 改成 `/usr/local/bin/card` 真脚本。函数只活在定义它的那一个
   shell 里 —— 录屏、子 shell、claude-code 的 Bash 工具里全都没有。
   做成脚本，这些地方一次全好。
2. `microclass-record` 的 `--command` 从 `$SHELL -i` 改成 `$SHELL -il`。
   **录到的 shell 必须和学员平时那个 shell 一模一样**，否则证据里那个环境
   和交付的环境是两个东西（banner、配置渲染都不在录屏里）。
   加 `-l` 不递归：`ASCIINEMA_REC=1` 那道守卫实测有效 —— 真 pty 跑完
   退出码 0，cast 里 banner 恰好 1 次。

### bug 2：交付路径里从来没有投放测评任务这一步

`/workspace/task-a` 只有仿真器 `simulate.py` 会 `docker cp` 进去。
真走 `sandctl create` 开出来的测评号，学员登进去 `/workspace` 是空的。
之所以一直没暴露：唯一跑过测评的那个号是仿真器起的。

修：`sandbox.seed_task()` + `sandctl create` 在测评模式自动投放，
另有 `sandctl seed` 作为活容器的修补口（不必重建容器）。
初始提交不是可选项 —— 批改的证据源 ② 是"和基线的 diff"，没有基线那条证据整条哑。

### 体检新增的两项

| 查什么 | 怎么查 | 为什么这么查 |
|---|---|---|
| `card` | **裸 `bash -c 'card'`**，不读 profile | 那就是当年出事的那种 shell。用登录 shell 查会假绿：`type card` 在那里说"是个函数"，看起来完全正常 |
| 测评任务 | 目录在 + `git rev-parse HEAD` 通 | 只查目录在会漏掉"有题但没基线提交"，那种情况证据源 ② 照样哑 |

三次破坏实测（改回函数 / 删任务目录 / 删 `.git`）全部转红，还原后回绿。

### 前置检查：没题就别开号

`sandctl create` 会在**动任何资源之前**确认这一轨有题。
先建容器、发 key、存档案、再发现没题可投，留下的是一个半成品学员
加一把活着的网关 key。实测踩过：轨道 B/C 的题还没写，`stu-c`/`stu-d`
就是这么卡住的。

**目前只有 `task-a`。轨道 B/C 开不出号，这是对的 —— 题还没写。**

### 可执行位：别再靠"记得同步"

`COPY --chmod=0755 rootfs/usr/local/bin/`。这里连栽两次：先是写死名单
（漏了 `microclass-doctor`），改成 `chmod microclass-*` 之后又漏了 `card`
—— 它不叫 `microclass-*`。任何"记得同步一下模式位"的方案迟早会漏，
所以让它没有可漏的地方。

## 各工具怎么接到网关的

一处来源 → `microclass-config` 渲染各工具原生配置。这是 cc-switch 的思路做成脚本：
cc-switch 本身是 Tauri 桌面 GUI（沙盒无图形环境），而且它把 key 收在自己库里由
proxy 注入，会打掉「每人一把网关 key」—— 那是计费归属和毕业吊销的根基。

| 工具 | 怎么配 | 状态 |
|---|---|---|
| claude-code | `ANTHROPIC_BASE_URL` / `_AUTH_TOKEN` / `_MODEL` 三个环境变量 | 通 |
| hermes | `~/.hermes/config.yaml` 的 `providers.microclass`（`key_env` 引环境变量，明文 key 不落盘） | 通 |
| codex | `~/.codex/config.toml`，`wire_api = "responses"` | **不通**，见下 |
| lark-cli | 不走模型网关，走飞书开放平台 | 只验到「能跑」 |

### hermes 的两个坑（都实测过）

1. **`/opt/hermes/bin/hermes` 是个降权 shim**，`docker exec` 以 root 进来时它会切到
   uid 10000。而 `$HOME` 在持久卷上是 `root:root 755` —— 降权之后它连自己的
   `HERMES_HOME` 都建不出来，报 `Errno 13`。那个 shim 存在的理由是和 s6 监管的
   gateway 进程对齐 uid，**我们的容器 PID 1 是 ttyd，根本没有那个进程**。
   用它自带的 opt-out：`HERMES_DOCKER_EXEC_AS_ROOT=1`（sandctl 注入）。
2. **它不认 `OPENAI_API_KEY` 这类通用变量**，要自己的 `providers` 段，否则
   `HTTP 401: Missing Authentication header`。

> 走过的弯路，留着省下次的时间：先怀疑是 `HERMES_WRITE_SAFE_ROOT=/opt/data`
> 这个写入白名单，**实测推翻**（指到 `/workspace` 照样失败）。做了个 2×2
> （卷/overlayfs × 点目录/普通目录）才定位到变量是「卷」不是「目录名」，
> 最后在 shim 的注释里找到真答案。

### codex 走的是 Responses API，不是 Chat

codex 0.137+ 删掉了 `wire_api = "chat"`，只认 Responses API。
实测一路回退到 0.138.0 都已经删除，**回退版本不是出路**。

网关已经补上 `/v1/responses`（Responses ↔ Chat 双向翻译）。
2026-08-21 实测：`POST /v1/responses` 返回 200，纯文本路径吐出契约里那 9 个事件
（`response.created` → … → `response.completed`），`microclass-doctor` 里
codex 那项已转绿。

契约（抓真流量 + 拿真 codex 当验收器验出来的）和实现说明在
`llm-gateway/docs/design/responses-api.md`。

`versions.lock` 是**唯一真源**。改它 → 重建 → 所有人环境同时换版。**模型也在里面**（`MODEL=`）——
模型和工具版本同属单版本策略，不在两处各写一份，那样迟早会漂。
`microclass-doctor` 会拿它去网关 `/v1/models` 实际核对，名字对不上直接红。
不存在多版本共存（设计文档 §7）。

镜像内的 `microclass-selfcheck` 断言实际版本与 lock 一致，
**构建期不符直接中止构建** —— 否则 lock 会变成一句谎话，
而哨兵 cron 正是拿它当真源做 diff 的。asciinema 走 apt，尤其需要这条断言。

`sandctl` 交付容器给学员之前也会复跑同一个 selfcheck。

## 覆盖了基底的 ENTRYPOINT

基底的 ENTRYPOINT 会拉起 s6 监督树（需要 root，且以非 root 用户启动会直接 exit 143）。
学员沙盒里 hermes 是当 CLI 用的、不是当 daemon，所以 `ENTRYPOINT []` + `CMD ["/bin/bash","-l"]`。

注意：`docker run <img> -c '...'` 会把 CMD **整个替换掉**（argv[0] 变成 `-c`）。
要测默认 CMD 得喂 stdin：`echo '...' | docker run -i <img>`。
