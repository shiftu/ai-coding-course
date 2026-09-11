# sandctl —— 学员沙盒生命周期

```
./sandctl create <学员> [--mode assessment|course] [--track A|B|C]
./sandctl list | info | url | start | stop | selfcheck | graduate | destroy <学员>
./sandctl bind   <学员> --lark-open-id <飞书 open_id>
./sandctl module <学员> <模块id> --state exempt|pass|reset [--by 谁判的]
./sandctl module-evidence <学员> [模块id] [--limit N]   # 验收前先看线索（只读）
./sandctl capacity [--apply-limits]                     # 这台机器还能开多少人
python3 e2e.py          # 端到端验收，25 项
python3 test_module_evidence.py   # module-evidence 的离线测试
```

一名学员 = 一个容器 + 一个持久卷 + 一个只听回环的 ttyd 端口 + **一把自己的网关 key**。
状态一人一个 JSON 文件（`~/.local/state/microclass/`），没有数据库 ——
每周约 2 个新人，`cat` 一下就能看懂比什么都强。

## 每人一把网关 key

设计文档 §1.1 的工程清单里漏了这件事，spike 时补上的。它有两个作用：

1. **归属**：`list_request_logs --key-id` 能把网关调用精确归到某个人，
   这是证据链四件套里的第四件（§4.3）。
2. **开关**：吊销它 = 停止采集。§8「毕业即零采集」靠的就是这一下。

明文只在签发时返回一次，落到 `~/.local/state/microclass/secrets/<学员>.key`（0600），
不进状态文件。容器创建失败会回滚吊销，不留活 key。

## graduate 的顺序不能调换

**先停容器，再吊销 key。** 原因是网关的一个真实缺陷：

`llm-gateway` 的鉴权走一层 60 秒 TTL 的内存缓存（`internal/auth/cache.go`）。
`internal/server/auth.go` 的 `handleAPIKey`：

```go
ak, cached := a.cache.Get(prefix)
if !cached {
    row, err := a.store.LookupAPIKeyByPrefix(prefix)  // 只有这条路径看 revoked_at
    ...
}
...
a.cache.Put(ak)   // 每次鉴权成功都把 expiresAt 重新推后 60 秒
```

命中缓存时**根本不查库**，而 `revoked_at` 只有库那条路径看得到；
更要命的是每次成功鉴权都会给缓存续命。于是：

> **一把持续在用的 key，被吊销后可以无限期继续生效。**

实测（2026-08-20，本机网关）：

| 动作 | 结果 |
|---|---|
| `revoke_api_key` | `{"ok": true}`，DB 里 `revoked_at` 已写入 |
| 立刻用这把 key 请求 | **HTTP 200** |
| 每 10 秒探一次、连探 89 秒 | **一直 200**（探测本身在续命） |
| 停掉容器、静默 75 秒后单发一次 | **HTTP 401** ✅ |

对照组：伪造 key → 401，空 key → 401。所以不是「鉴权没开」，
是**吊销在请求路径上不生效**。

先停容器就切断了唯一还在用这把 key 的东西，缓存不再续期，
一个 TTL 后 `revoked_at` 生效。`e2e.py` 用 `200 → 401` 的前后对照证明了这一点。

**这个缺陷本身建议在 llm-gateway 里修**（`Put` 时带上 `revoked_at` 判断，
或者 revoke 时主动 invalidate 缓存条目）—— 但那是另一个仓库的事，
微课堂这边先按上面的顺序把边界兜住。

## 两个「差点写成假题」的坑

1. **判断吊销成功，不能用「key 还在不在列表里」**。吊销后它**仍然在列表里**，
   只是多了个 `revoked_at`。用存在性判断会永远报「吊销失败」。
   → `gateway.key_active()` 看的是 `revoked_at`。

2. **反向验证不能拿空 key 去问**。第一版 e2e 在 graduate 之后才取 key，
   那时明文已经删了，取到空串 —— 测的其实是「空 key 被拒」，
   而空 key 本来就会被拒。必须在毕业**之前**把明文抓在手里，
   前后对照同一把 key 同一条请求。

## bind / module —— 给 web 前端用的两条

**`bind`**：把飞书 open_id 绑到学员档案上。web 前端**只认这一处映射** ——
SSO 成功后拿 open_id 反查档案，查不到就把 open_id 显示给用户去找管理员。
故意不做自助开通：否则任何能走完 SSO 的人都能建容器，把宿主机的卷和端口耗光。
一个 open_id 只能绑一名学员，重复绑会被拒。

**`module`**：记一个模块的通过状态。这是「我的轨道」页面上进度的**唯一**来源。
没有记录 = 未开始 —— 前端不从容器活动、证据或任何别的地方推断进度。
推断出来的进度会让人以为自己学过了。`--state reset` 清掉记录。

## module-evidence —— 验收前先看线索

`module` 的判定依据是轨道文件里那行 `exempt_test`（设计文档 §5：每个模块一个
10 分钟迷你实操，通过即跳过）。§5.2 写的"交付物 → 批改 agent 打分"目前只对**测评**
实现了，模块验收是纯人工 —— 管理员得自己翻 harvest 目录里的 jsonl、回放 .cast。
这条命令把「翻」收掉：

```
./sandctl module-evidence stu-x              # 整条轨道：每个模块三路命中数
./sandctl module-evidence stu-x m3-hermes    # 细看：哪个时刻、哪份记录里出现过
```

**它不判定、不写档案。** 出来的是线索，免修与否仍然按 exempt_test 人工验收，
验过再 `module … --state exempt`。自动把线索当结论，就是上一节那句「推断出来的进度」。

三路来源，各有盲区，盲区印在输出里而不是默默留空：

| | 来源 | 盲区 |
|---|---|---|
| ① | 卷里 `.claude/projects/**/*.jsonl` | 只有 claude-code |
| ② | 卷里 `.codex/sessions/**/*.jsonl` | 只有 codex |
| ③ | `/evidence/*.cast` | 覆盖终端里的一切（含 hermes），但 §4.3 **只在测评模式录** —— course 模式要 `create --record` 才录，否则这一路天然是空的 |

录屏里「学员敲的」和「程序打印的」分开数：提示符（`root@…#`、`>`、`hermes>`）后面的算敲，
其余算输出。分开是因为 `lark-cli --help` 里也有 profile 和 skills 两个词 ——
第一版没分，m3-hermes 在 stu-x 身上"命中 696 处"，其中 680 多处是帮助文本和登录横幅。
提示符出现之前的输出（登录横幅，MOTD 里就把四件工具的名字都印了）一律不算。

关键词表在 `module_evidence.PATTERNS`，按模块 id 建（同一个模块在 A/B/C 里
`exempt_test` 一字不差）。`test_module_evidence.py` 钉住了「三条轨道的每个模块
都登记过」—— 新加模块忘了登记，测试挂，而不是验收时静默无命中。
读卷（① ②）是采集，毕业后按 §8 不再做；录屏是课程期内已落盘的既有证据，照旧可看。

## showcase —— 把一段录屏挑进精选案例库

设计见 `docs/design/cast-replay-showcase.md`。学员在"我的证据"页只能看**自己**的录屏；
要让好例和反例给所有人看，走这一条命令，也**只有**这一条：

```
./sandctl showcase stu-x session.cast --module m3-hermes --as good \
    --title "新会话验证记忆生效" --slug memory-verify --by panda [--source teacher]
```

它做四件事：从学员证据目录读源文件 → `redact.py` 脱敏 → 写到
`curriculum/showcase/<模块>/<good|bad>-<slug>/`（`session.cast` + `case.yaml` + `notes.md` 模板）
→ 打印接下来人要做的三步。**不 commit。**

三道闸，缺一不可：

1. 只有管理员能跑（web 没有入口）；
2. 副本经脱敏，原文件不动 —— 脱敏器只认已知模式（密钥前缀、学员 ID、网关地址、
   飞书 open_id），一个密钥被终端拆成两段输出它就看不见，所以**挑的人必须从头看一遍**。
   `notes.md` 模板第一行就是这句，`validate.py` 会拦下还带着这句的案例；
3. 走 git 提交，PR 就是审核。`cd curriculum && python3 validate.py` 顺手校验
   `case.yaml` 五个字段、模块存在、录屏是可回放的 v2、讲解非空。

老师不单独录"示范"：老师就是一个测评沙盒账号（`create teacher-x --mode assessment`），
录出来的东西和学员一样走这条命令，只是 `--source teacher`。理由：少一套数据结构、
少一个入口，而且老师录到的环境和学员看到的保证一致（上面那次 `-il` 事故的教训）。

课程模式默认不录屏。要收课程期的案例，开号时加 `--record`：
`create stu-y --mode course --track B --record`。测评模式不看这个开关，一律录。

## ttyd 挂在 /t 下，不是根路径

`sandbox.TTYD_BASE_PATH = "/t"`。ttyd 页面引用的是绝对路径（`/ws`、`/token`），
挂在根上时反代出去这些资源会 404。前端和容器共用这一个常量。

`create` 会把当时的前缀记进档案（`ttyd_base_path`）。**改这个常量是破坏性的**：
老容器仍挂在老前缀上，前端检查到对不上就直说「要重建」，而不是给白屏。
重建：`sandctl destroy <学员> --keep-volume` 再 `sandctl create <学员>`，卷不会丢。

## capacity —— 这台机器还能开多少人

```
./sandctl capacity                        # 只读
./sandctl capacity --mem-limit 3g         # what-if：新开的容器按 3g 算，不动任何东西
./sandctl capacity --apply-limits         # 给加上限之前开出来的老容器补资源上限
./sandctl create stu-y --mem-limit 3g     # 单独给某人开大（默认 2g）
```

设计文档里「64G 撑 30 并发」是拍脑袋的。这条命令给两条可复算的线：

- **硬上限** = 已开容器各自的上限累加，剩余预算再除以「新开的每个多大」。所有人同时吃满也拖不垮宿主机的人数。
  不是「常量 × 人数」：有人用 `--mem-limit` 单独开大之后两种算法就对不上了，报告读的是每个容器
  `HostConfig.Memory` 的地面真相。没上限的老容器按新开的值记。
- **实测余量** = (总内存 − 预留 − 已用) / 活跃容器平均占用。按现在真实用法还能塞几个，乐观值。

`--mem-limit` 不给就是 `sandbox.MEM_LIMIT`（2g）。只认 docker 写法（`3g`、`512m`、纯字节数），
写错在动任何资源之前就报错。进程数上限不开口：512 已经远高于实测 145，没有调它的理由。

数据全来自 `docker info` / `docker stats` / `docker system df`，没有估算参数写死在别处。
CPU 不算：agent 大部分时间在等 LLM 响应，实测活跃容器不到 5%；真正的瓶颈更可能在网关的
并发和 token 配额。磁盘那行才是要提前规划的 —— 镜像只算一份，持久卷按人头长。

**每个容器有硬上限**（`sandbox.MEM_LIMIT = 2g`、`PIDS_LIMIT = 512`，`--memory-swap`
等于 `--memory` 所以是真硬的）。依据：实测活跃沙盒（claude + hermes 同时跑）约 950 MiB、
145 个进程，空闲只有 ttyd + bash 约 20 MiB。没有上限时「硬上限」那行不成立 ——
一个跑飞的进程能把整台机器拖垮，其他人一起掉线。老容器用 `--apply-limits` 补，
`docker update` 即时生效，不重启、不丢会话 —— **前提是它当前占用没超过上限**。
超过的会被跳过并告警：cgroup 上限一落地就 OOM，杀到 ttyd 整个容器重启，会话就没了。
等它降下来再跑一次，或者 `destroy --keep-volume` + `create` 重建。

## 容器长什么样

- ttyd 是 PID 1，每次浏览器连接 spawn 一个登录 shell；`-c 学员:随机口令` 鉴权，
  只绑 `127.0.0.1`，对外靠 web 前端反代。
- 每个容器 `--memory 2g --memory-swap 2g --pids-limit 512`（见上面 capacity 一节）。
- `/workspace` 是持久卷，且 `HOME` / `CLAUDE_CONFIG_DIR` / `HERMES_HOME` 都指过去 ——
  代码、claude 会话记录、hermes 状态跟着人走。
- `/evidence` 是宿主机 bind mount，录屏直接落到宿主机，harvest 不用 `docker cp`。
- `--mode assessment` 时登录即自动 asciinema 录制（§4.3 只测评录，课程期不录）。
- 交付给学员之前 `create` 会在容器里跑一遍镜像自检，不过就不交付。

---

# harvest —— 取证据链

```
python3 harvest.py <学员> [--out 目录]
python3 simulate.py <学员> [--persona diligent|hasty]   # 造一份真实证据（真跑模型）
```

四类证据（§4.3），全是**本来就落在那里**的东西，测评结束后一次性读取：

| | 来源 | 怎么取 |
|---|---|---|
| ① | claude-code 会话记录 | 从持久卷 tar 出 `.claude/projects/**` |
| ② | git 仓库状态 | 每个仓库存 log / status / diff / diff-staged / branch |
| ③ | asciinema 录屏 | 本来就 bind mount 在宿主机，只清点不搬家 |
| ④ | 网关请求日志 | 按这名学员的 `api_key_id` 过滤 |

容器停着也能取 —— 挂个一次性容器读卷就行，不要求容器在跑。

**存 status 而不只是 diff**：学员改完可能直接 commit 了，那时 diff 是空的，
只看 diff 会得出「什么都没改」——又一个空集陷阱。

**毕业后拒绝执行**，退出码 1。§8 的硬边界不能只写在文档里：

```
$ python3 harvest.py harvest-test
错误：harvest-test 已于 2026-08-20T13:41:13Z 毕业 —— §8 硬边界：毕业后零采集，拒绝执行。
```

`manifest.json` 里有一个 `empty_sources` 列表，明确记下哪几路是空的 ——
空证据必须是**显式结论**，不能让下游默默当成「这人没问题」。

## 真实证据跑出来的第一个发现

`simulate.py` 造的第一份真实证据，直接打掉了 rubric 的一个必然误判：

`safety/no-secret-literal` 原来扫**整个** tool_use input。而 Edit 的 `old_string`
是**被替换掉的原文** —— 测评仓库 README 里预埋的那个假密钥（这是故意的埋点），
学员去改它的时候，那串字符必然出现在 `old_string` 里。

**结果是每一个学员都会被判密钥泄露**，包括正确处置的那些。

修法：只扫「学员写下的字段」——`Bash.command` / `Write.content` /
`Edit.new_string` / `MultiEdit[].new_string`，明确排除 `old_string` 和 tool_result。
判定口径已写进公开的 `rubric.md`（学员看得到自己按什么被判）。

配了三条 fixture 钉住这个边界：`secret-clean`（读到并改掉 → pass）、
`secret-in-command`（敲进命令行 → fail）、`secret-in-write`（写进 .env → fail）。

修完之后同一份真实证据仍然 `fail` —— 而这次是**对的**：学员重写了 README 里
那段代码块（把过时的 `python weekly.py` 改成了 `python -m weekly_report.cli`），
却把紧挨着上一行的 `export LARK_APP_SECRET=sk-live-...` 原样留下了。
他手指头就在那一行上，没看见。这正是 S1 埋点想抓的东西。

## 采证必须在静止态做

`harvest` 默认**拒绝**在容器里还有 agent 进程时采证，退出码 1。
用 `--stop-first` 先停容器（推荐，`run.sh` 就是这么调的），
或 `--allow-live` 明确接受半截证据（会记进 manifest 的 `quiescent` 字段）。

**为什么要这条**：`claude -p` 返回之后，它的工具调用不一定落完盘；
学员从 ttyd 断开也不代表 agent 停了。实测踩过一次 ——

| 采证时刻 | git 状态 | 批改结论 |
|---|---|---|
| 041002Z | 0 处改动 | 交白卷，质量验证未测得 |
| 041134Z | 13 行 diff | 质量验证 **L2** |

**同一名学员、同一份作业，两个结论。** 判定必须可复现，
所以采证必须在静止态做。三个方向都验过：静止能采、有 agent 拒绝且退出码 1、
`--stop-first` 能采且 `quiescent=True`。
