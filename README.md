# AI 微课堂

面向团队内部的 AI 能力加油站：**自愿来、随时走**。用一次 33 分钟的沙盒实操摸底（看行为，不是答题），
按短板给课，内容跟着工具版本走。规模假设是约 100 人/年、峰值并发 30 —— 精品小班，不是公共平台。

仓库里没有任何一家公司的域名、内网地址或密钥：要跑起来只需要 Docker 和一个
[llm-gateway](https://github.com/shiftu/llm-gateway)，其余外部服务都是可选的，见「外部依赖」。

一名学员的完整路径：

```
测评        开一个沙盒容器，20 分钟做一个"接手旧仓库"的复合任务
  ↓
批改        读证据链（会话记录 / git / 网关日志 / 录屏），按公开 rubric 判定
  ↓
分轨        四维向量 + 安全闸结果 → A（零基础）/ B（有基础）/ C（资深）
  ↓
学习        轨道引用切片，每个模块开头一个免修考，通过即跳过
  ↓
毕业        吊销网关 key，采集归零 —— 这是硬边界，不是配置项
```

四个设计原则贯穿全仓，读代码时会反复撞见：**行为证据优先**、**不监控员工（毕业即停止采集）**、
**内容即代码**、**纯终端**。

---

## 仓库结构

```
curriculum/          课程内容（纯内容 + 校验/批改脚本，不含运行时）
  slices/              56 条切片 —— 最小教学单元，路径即 id
  tracks/              3 条轨道 —— 把切片排成模块顺序
  assessment/          测评任务仓库 —— A/B/C 三个同构变体
  rubric/              判定表 + 批改器 —— rubric.md 是唯一真相
  showcase/            精选案例（脱敏录屏 + 讲解）—— 目前是空的
  validate.py          结构校验 + 内容保鲜机验

platform/            平台运行时
  control/             sandctl —— 学员沙盒生命周期、采证、容量
  sandbox/             学员容器镜像（Docker，linux/arm64）
  web/                 学员的 5 个页面（纯标准库，无构建步骤）
  skills/              microclass-grade —— 批改 agent 的 Hermes skill

docs/design/         设计文档（先读 platform-design-v1.1.md）
index.html           产品概览单页，直接 open 就能看
```

每个子目录都有自己的 README，写得比这份详细，也更坦白 —— 踩过的坑都记在里面。

---

## 快速开始：只想看看，不装 Docker

三条命令，全程离线、零依赖、不碰容器：

```bash
open index.html                                    # 产品概览

cd curriculum && python3 validate.py               # 课程结构校验（约 1 秒）

cd platform/web && python3 serve.py --dev-login    # 起 web 前端
```

然后开 http://127.0.0.1:7900/ ，填任意学员 ID 就能进。

`--dev-login` **等于没有认证**，所以它有三道闸，缺一不可：必须显式打开、必须只监听回环、
必须没配飞书应用（配了说明这是正式环境，直接拒绝启动）。

这条路走不到沙盒 —— 没有容器，测评页点"开始"会失败。要完整跑通看下一节。

---

## 完整安装

### 前置条件

| 依赖 | 要求 | 说明 |
|---|---|---|
| Python | 3.x | 平台层**只用标准库**，没有 requirements.txt，不用建虚拟环境 |
| Docker | 带 buildx | 镜像基底用了 `COPY --chmod`，需要 BuildKit |
| 架构 | linux/arm64 | 镜像只构建 arm64 |
| LLM 网关 | [llm-gateway](https://github.com/shiftu/llm-gateway) | **不在本仓库**，必须先跑起来（默认宿主机 `127.0.0.1:7421`） |
| hermes 基底镜像 | 本地已有 | `versions.lock` 里的 `HERMES_BASE`，从 [hermes-agent](https://github.com/NousResearch/hermes-agent) 源码构建，见 `platform/sandbox/README.md` |

### 外部依赖

| 服务 | 必需？ | 用在哪 | 换成你们自己的 |
|---|---|---|---|
| [llm-gateway](https://github.com/shiftu/llm-gateway) | **必需** | 每人一把 key、调用日志（证据源 ④）、毕业吊销、批改 judge | 跑一个实例，建 team，把 admin token 放到 `~/.config/llm-gateway/token` |
| Docker | **必需**（沙盒） | 学员容器 | Docker Desktop / OrbStack / colima / Linux 原生都行 |
| [hermes-agent](https://github.com/NousResearch/hermes-agent) | **必需**（沙盒） | 沙盒基底镜像 | 按 `platform/sandbox/README.md` 从上游源码构建 |
| 飞书（Lark） | 可选 | web 前端 SSO；沙盒里的 `lark-cli` 课程切片 | 不配就用 `--dev-login`；lark 切片不装飞书凭证只能验到"命令能跑" |
| Gitea / GitHub | 可选 | 课程内容里的练习仓库、Milestone、打卡 Issue | 只是课程文案（`index.html`、`curriculum/slices/tool/gitea-*`），换成你们的代码托管即可 |

模型名是网关里的**别名**，不是厂商原名：`versions.lock` 的 `MODEL` / `CODEX_MODEL`、批改用的 `JUDGE_MODEL`
都必须出现在你的网关 `/v1/models` 清单里（`microclass-doctor` 会实际核对）。仓库里写的是参考部署的别名，
按你的网关改。

### 环境变量

平台层没有配置文件，全部走环境变量，默认值都是"网关跑在同一台机器的回环上"：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MICROCLASS_GATEWAY_ADMIN` | `http://127.0.0.1:7421` | **宿主机**看网关的地址（sandctl 签 key、拉日志用） |
| `MICROCLASS_GATEWAY_TOKEN_FILE` | `~/.config/llm-gateway/token` | 网关 admin token 文件 |
| `MICROCLASS_TEAM` | `microclass` | 学员 key 归属的网关 team slug |
| `MICROCLASS_GATEWAY_HOST` | `host.docker.internal` | **容器**看网关的主机名。默认值在 Docker Desktop / OrbStack / colima 天然可解析，Linux 原生 docker 由 `--add-host …:host-gateway` 兜底（此时网关要监听 `0.0.0.0` 或 docker0，不能只听回环） |
| `MICROCLASS_GATEWAY_PORT` | `7421` | 容器看网关的端口 |
| `MICROCLASS_STATE` | `~/.local/state/microclass` | 学员档案、key、证据的落盘目录 |
| `MICROCLASS_LARK_APP_ID` / `_APP_SECRET` | 空 | 配了就是正式环境（飞书 SSO），`--dev-login` 会拒绝启动 |
| `MICROCLASS_WEB_BASE` | 空 | 对外地址，拼 SSO 回调用 |
| `LLM_GATEWAY_URL` / `JUDGE_MODEL` | `http://127.0.0.1:7421` / 见 `judge.py` | 批改 judge 走的网关和模型别名 |
| `MICROCLASS_SMOKE_KEY` / `MICROCLASS_SMOKE_MODEL` | 空 / `versions.lock` 的 `MODEL` | `smoke.sh` 端到端那一项 |

### 一、构建沙盒镜像

```bash
cd platform/sandbox
./build.sh        # 版本全部读 versions.lock，不接受命令行覆盖
./smoke.sh        # 冒烟；端到端那项要 MICROCLASS_SMOKE_KEY
```

首次构建 15–45 分钟。`versions.lock` 是环境版本的**唯一真源**（claude-code、codex、lark-cli、
ttyd、glow、pytest、asciinema，以及统一模型），改它等于改所有人的环境。

镜像 tag 是 `./stamp.sh` 算出的 12 位构建戳，戳 = `versions.lock` + `Dockerfile` + 整个 `rootfs`
的哈希。**tag 只是名字，image id 才是身份** —— 这一条在生产上踩过，原因写在 `platform/sandbox/README.md`。

### 二、开第一个学员

```bash
cd platform/control
python3 sandctl create stu-a --mode assessment --track A
```

它会依次：查网关健康 → 查这一轨有没有题 → 发网关 key → 起容器 → 投测评任务 →
跑镜像自检 → 跑运行期体检 → 打印终端地址和口令。任何一步不过就不交付，不留半成品。

容器只监听回环，对外由 web 前端反代。

### 三、起 web 前端

正式环境用飞书 SSO，两个环境变量：

```bash
export MICROCLASS_LARK_APP_ID=...
export MICROCLASS_LARK_APP_SECRET=...
cd platform/web && python3 serve.py --host 0.0.0.0 --port 7900
```

对外请用 nginx/Caddy 做 TLS 终止再反代，并把 `X-Forwarded-Proto` 传进来。

学员用飞书登录后，靠 `sandctl bind <学员> --lark-open-id <id>` 建立的映射认人。
**故意不做自助开通** —— 否则任何能走完 SSO 的人都能建容器。

---

## 日常运维

```bash
cd platform/control

python3 sandctl list                      # 全部学员
python3 sandctl info <学员>               # 看档案
python3 sandctl url <学员>                # 终端地址与口令
python3 sandctl doctor <学员>             # 运行期体检：每件工具真发一次请求

python3 sandctl capacity                  # 这台机器还能再开多少人
python3 sandctl image-audit               # 档案里的镜像身份 vs 容器实际在跑的

python3 sandctl module <学员> <模块id> --state pass --by <管理员>
python3 sandctl graduate <学员>           # §8 硬边界：吊销 key，采集立即归零
```

批改一名学员（**不要**顺手 `graduate`，那是毕业边界不是批改步骤）：

```bash
python3 harvest.py <学员>                                   # 采证到时间戳目录
python3 ../../curriculum/rubric/grade.py <harvest目录> \
        --student <学员> --out <harvest目录>/grade          # 产出 grade.json + debrief.md
```

状态全部落在 `~/.local/state/microclass/`（可用 `MICROCLASS_STATE` 改）：一人一个 JSON 文件，
没有数据库 —— 每周约 2 个新人，用不着。

---

## 参与开发

### 跑测试

十一个离线检查，都不碰 Docker、不打网络：

```bash
cd curriculum       && python3 validate.py
cd curriculum/rubric && python3 test_grade_rules.py
cd curriculum/rubric && python3 test_judge_guard.py
cd curriculum/rubric && python3 test_calibrate.py
cd curriculum/rubric && python3 test_task_routing.py
cd platform/control && python3 test_capacity.py
cd platform/control && python3 test_module_evidence.py
cd platform/control && python3 test_redact.py
cd platform/control && python3 test_showcase.py
cd platform/web     && python3 test_web.py
```

测评变体的不变量检查要 pytest，宿主机上通常没有，加 `--no-pytest` 可以只跑不依赖它的那几项：

```bash
cd curriculum/assessment && python3 verify_tasks.py --no-pytest
```

它查的是三个变体的对称性：恰好一条测试挂、假密钥必须命中打分器自己的正则、三轨的密钥形态和
歧义词互不重叠、学员可见文件里不出现「测评 / 埋点 / rubric」字样。**没 pytest 时它判失败而不是
静默跳过** —— 完整跑一遍要在沙盒容器里。

要真的开容器、真的调模型的验收，另有两个（会花网关的钱）：

```bash
cd platform/control
python3 e2e.py                     # 开号 → 用 → 毕业 → 销号，每步验真
python3 simulate.py <学员>         # 真跑 claude-code 做完测评，产出真实证据链
```

### 几条贯穿全仓的约定

**单一真源，不许有第二处。** 环境版本只在 `versions.lock`；rubric 的维度和等级边只在
`rubric.md`（`grade.py` 用正则解析那一行，改文档就改了逻辑）；轨道进度只认 `sandctl module`
写下的记录，不从容器活动或证据里推断。

**空集不是通过。** 证据为空要显式记成"未测得"，不能默认成"这人没问题"。
一条等级边上全是 n/a 就是未测得，既不判过也不判 L0。

**装上了 ≠ 跑得通。** 自检只断言版本号，体检才真的让每件工具发一次请求。
codex 和 hermes 曾经坏着而自检全绿，一路发到学员手里。

**机验必须按 env 过滤。** 切片分 `container` 和 `own-mac` 两种环境，
`own-mac` 的机验在容器里跑必然失败 —— 那是假警报，会让哨兵 Issue 迅速失去可信度。

**脱敏器不是闸，人才是。** `sandctl showcase` 只认已知模式，一个密钥被终端拆成两段它就看不见。
入库后必须有人从头看一遍录屏，写完 notes.md 再提 PR，PR 就是审核。

### 提交约定

本仓库用 [keel](https://github.com/shiftu/keel) 保存目标、约定和验证证据，约定写在 `AGENTS.md` / `CLAUDE.md`
（由 `keel sync` 生成，要改改 `.keel/`）。

```bash
keel why --path <路径>              # 改之前先查这块有什么决定
keel check --target index           # 提交前
```

四类动作要记决策并在提交信息里带完整 trailer `Decision: D-<uuid>`：加换依赖、跨两个以上模块的
结构选择、改公开接口或数据格式、改构建或部署方式。结论能跑命令验证的就跑 `keel verify`，
没有"登记一条我认为它通过了"。

---

## 现状与已知局限

这些子 README 里写得很坦白，这里汇总一下，避免新人误以为是成熟系统：

- **真人标定数据一份都没有。** rubric 里 `spec/scope-control` 的 fixture 全是合成的。
- **标定小组规模已知不够。** 算下来三变体需要约 24 人，设计文档写的是 10–15 人，两条路
  （扩人 / 受试者内设计）必须开标定前先选一条。
- **rubric 缺「需求表达」的 L0→L1 锚点**，是个真缺口。
- **精选案例库是空的。** 设计定稿、入库工具就绪、内容还没有。
- **容量估算的硬上限是内存维度的。** 真正的瓶颈更可能是网关的并发和 token 配额，`capacity` 不覆盖。
- **macOS 上 `docker info` 报的是虚拟机，不是你的 Mac。** Docker Desktop / colima 下容量按 VM 的配额算，
  要开大得调 VM（colima 是 `colima start --cpu N --memory M`）。
- **课程文案里的组织名和仓库名是示例。** `index.html` 和部分切片提到的 `ai-workshop/playground`、
  Gitea Milestone、PostHog 等，是参考部署的做法，换成你们自己的即可，平台代码不依赖它们。

---

## 文档索引

| 文档 | 讲什么 |
|---|---|
| [docs/design/platform-design-v1.1.md](docs/design/platform-design-v1.1.md) | **从这里开始** —— 精简版设计，砍了什么、什么信号出现时建回来 |
| [docs/design/platform-design-v1.md](docs/design/platform-design-v1.md) | v1.0 原版，看被砍掉的部分当初是怎么想的 |
| [docs/design/cast-replay-showcase.md](docs/design/cast-replay-showcase.md) | 录屏回放与精选案例库方案 |
| [spike-feasibility-2026-08-20.md](spike-feasibility-2026-08-20.md) | 投不投的可行性验证结论 |
| [curriculum/README.md](curriculum/README.md) | 为什么课程按天组织、切片按维度组织 |
| [curriculum/rubric/README.md](curriculum/rubric/README.md) | 判定表怎么运作，聚合的四条硬规矩 |
| [curriculum/assessment/README.md](curriculum/assessment/README.md) | 五个埋点，三个变体怎么换表皮不换考点 |
| [platform/control/README.md](platform/control/README.md) | sandctl 每条命令，以及 graduate 的顺序为什么不能调换 |
| [platform/sandbox/README.md](platform/sandbox/README.md) | 镜像身份、单版本策略、构建戳 |
| [platform/web/README.md](platform/web/README.md) | 页面与路由、认证 |
