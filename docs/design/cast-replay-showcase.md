# 录屏回放与精选案例（showcase）

> 日期：2026-09-10 · 作者：Panda（与 AI 协作产出）· 上游：platform-design-v1.1.md §4.3 信号采集、§4.4 打分与人工抽查

## 0. 一句话

**录屏已经有了，回放没有。** 本方案补三件事：网页内回放、精选案例库（好与坏都收）、课程期可选录制。老师不单独录"示范"——老师以学员身份进沙盒操作，录出来的东西和学员一样走精选流程。

## 1. 现状（代码里已经存在的）

| 环节 | 现状 | 出处 |
|---|---|---|
| 录制 | `microclass-record` 用 asciinema v2 录整个登录 shell（`-il`），落盘宿主机 `/evidence/<学员>/*.cast` | `platform/sandbox/rootfs/usr/local/bin/microclass-record` |
| 何时录 | **只在测评模式**（`MICROCLASS_MODE=assessment`），课程期一段都没有 | `profile.d/10-microclass.sh`，§4.3 |
| 回放 | 证据页只给下载链接，学员本机 `asciinema play` | `platform/web/pages.py` 证据段 |
| 可见范围 | `_cast` 路由白名单：只能取**自己**证据目录里的文件 | `platform/web/serve.py` |
| 老师示范 | 无 | — |
| 公开/精选 | 无 | — |

网页里没有播放器的原因是 CSP `default-src 'self'`，不能引外部 JS。这是一条正确的约束，方案不动它。

## 2. 取舍（先说不做什么）

- **不做"老师示范"这个独立概念。** 老师用同一个沙盒、同一个录制路径操作一遍，产物和学员的 `.cast` 一模一样，再由精选流程挑进 showcase。理由：少一套数据结构、少一个入口，而且老师录的东西和学员看到的环境保证一致（README 里那次 `-il` 事故的教训）。
- **不从学员证据目录直接公开。** §4.5 铁律"个人分数仅本人可见"，`.cast` 是分数的证据源，同样只本人可见。进 showcase 的是**脱敏后的副本**，且必须经人工挑选。
- **不做实时观摩。** ttyd 反代不做多人只读旁观。回放解决的是"事后看"，实时看是另一件事，目前没有需求。
- **不做自动判定"好/坏"。** 好坏由人标，批改 agent 的判定结果只作为挑选线索。

## 3. 方案

### 3.1 网页内回放（前提，先做）

- 把 asciinema-player（Apache-2.0，js + css 约 200 KB）**打进仓库** `platform/web/static/asciinema-player/`，版本写进文件名。同源加载，CSP 不改。
- 证据页的下载链接改为内嵌播放器；保留下载链接作兜底。
- 播放器开：倍速、进度条拖动、暂停后可选中复制文本（这是它比视频强的地方）。
- `serve.py` 已有的 `_cast` 路由改成同时支持 `Content-Disposition: inline`，播放器用 fetch 取同一个 URL。

验收：任一测评学员登录后能在证据页直接看自己的录屏，不装任何本地工具。

### 3.2 精选案例库（showcase）

**存放**：仓库内 `curriculum/showcase/<module>/<slug>/`，每个案例一个目录：

```
curriculum/showcase/m3-hermes/good-memory-verify/
├── case.yaml        # 元数据
├── session.cast     # 脱敏后的录屏副本
└── notes.md         # 讲解：为什么好 / 哪里坏、看的时候注意什么
```

`case.yaml` 五个字段，和切片 schema（§5.1）一样砍到最少：

```yaml
module: m3-hermes           # 挂在哪个模块
verdict: good | bad         # 好例还是反例
title: 新会话验证记忆生效
source: teacher | student   # 来源身份，不写具体是谁
picked_by: panda            # 谁挑的（管理员），可追溯
```

走 git 提交进仓库，PR 就是审核。这样案例和课程内容一起版本化，`curriculum/validate.py` 顺手校验 `module` 是否存在、`session.cast` 是否 v2 且 width > 0。

**入库命令**：`sandctl showcase <学员> <cast文件> --module <id> --as good|bad --title "..." --by <管理员>`

做四件事：读源 `.cast` → 脱敏 → 写到 `curriculum/showcase/<module>/<slug>/` → 生成 `case.yaml` 和空的 `notes.md`。**不 commit**，留给人看完 notes 写完再提交。

**脱敏**（`platform/control/redact.py`，纯函数，可单测）：

| 处理 | 规则 |
|---|---|
| 学员标识 | `MICROCLASS_STUDENT`、cast 头里的 `title`、提示符里的主机名 → `student` |
| 密钥 | 网关 key、`sk-`/`Bearer` 形态的 token、`.env` 回显 → `[REDACTED]` |
| 内网地址 | 网关 URL、Gitea 地址 → 占位域名 |
| 未知 | 脱敏器只负责已知模式；**入库前必须有人从头看一遍**，这条写进 notes.md 模板的第一行 |

脱敏后原文件不动，副本另存。脱敏器对已知模式的覆盖用测试锁住：每加一类泄露就加一条用例。

**展示**：「我的轨道」每个模块旁出"案例"入口，列出该模块下 good/bad 各几个，点进去是 3.1 的播放器 + notes.md 渲染。所有登录学员可见（内容已脱敏，不含分数）。

### 3.3 老师怎么进来

老师就是一个 `--mode assessment` 的沙盒账号（`sandctl create teacher-x --track B --mode assessment`）。老师操作完，管理员用 3.2 的命令挑进 showcase，`source: teacher`。

老师想加旁白，录制时在终端里 `echo "# 我先看测试再改代码"` 即可，回放里原样出现；细讲写进 `notes.md`。

### 3.4 课程期录制（可选，最后做）

现在只在测评录。要收集课程期的好/坏案例，加一个开关，两种粒度择一：

- **按沙盒**：`sandctl create ... --record`，写进档案 `rec["record"]`，注入 `MICROCLASS_RECORD=1`，profile.d 的守卫从"模式 = assessment"改为"模式 = assessment 或 RECORD=1"。
- **按模块**：track yaml 的模块加 `record: true`。粒度更细但要沙盒知道学员当前在哪个模块，现在没有这个信息，**先不做**。

选按沙盒。录制对学员透明，创建时告知即可（登录页那句"全程录屏 + 会话记录"已经在说）。

## 4. 顺序与工作量

| 步 | 内容 | 依赖 | 估计 |
|---|---|---|---|
| 1 | 内嵌播放器（3.1） | 无 | 半天 |
| 2 | `redact.py` + 测试 | 无 | 半天 |
| 3 | `sandctl showcase` + `validate.py` 校验 | 2 | 半天 |
| 4 | 轨道页案例入口 + 案例页 | 1、3 | 1 天 |
| 5 | 课程期 `--record`（3.4） | 无 | 1 小时 |

第 1 步不动任何数据结构，先做。第 5 步最简单但最后做：没有回放和精选，多录只是多占盘。

## 5. 已知限制

- `.cast` 只录终端**输出**（没开 `--stdin`），学员敲了什么靠回显推断；claude / hermes 的 TUI 大量重绘，回放时闪。`module_evidence.py` 已有"提示符之后才算学员敲的"过滤，案例页不做这个，原样播。
- 回放看得到"做了什么"，看不到"为什么"。notes.md 是必填，不是可选。
- `--idle-time-limit 3` 已在录制参数里，长停顿会被压到 3 秒，回放不会干等。
- 一个案例的 `.cast` 可能几 MB。仓库里放几十个没问题，上百个再考虑 LFS 或搬去证据目录。

## 6. 安全边界

- showcase 是**唯一**一条从证据目录到公开的路，且只能由管理员手动触发、经脱敏、经 git 审核。
- `_cast` 路由的白名单不变：学员仍只能取自己的。案例页走另一个路由 `/showcase/<module>/<slug>/session.cast`，只读仓库内目录，路径经 `sitepath` 校验。
- 脱敏器不是闸，人是闸。脱敏器漏了什么，责任在挑选人，`picked_by` 就是为这个留的。
