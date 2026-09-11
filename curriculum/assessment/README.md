# 测评任务仓库 · A / B / C 三个变体

对应设计文档 `docs/design/platform-design-v1.1.md` §4.2 的沙盒复合任务。
判定依据在 `../rubric/rubric.md`。

## 内容

| 路径 | 用途 |
|---|---|
| `task-{a,b,c}/` | 种子仓库本体（学员拿到的就是它） |
| `ISSUE-7.md` / `ISSUE-B.md` / `ISSUE-C.md` | Issue 正文，在 Gitea 上创建 Issue 时贴进去 |
| `debrief-{a,b,c}.md` | 复盘话术，测评结束后立即使用 |
| `scope/{a,b,c}.json` | 各变体的歧义清单，`judge.py` 判 `spec/scope-control` 用 |
| `verify_tasks.py` | 变体不变量检查（恰好一条挂、密钥形态互不相同……） |
| `runs/*.jsonl` | 验证用的真实运行记录（见下方验证结果） |

**`scope/` 是 `task-X/` 的兄弟，不是它的子目录 —— 这是故意的。**
`task-X/` 会被整个复制进学员容器，把歧义清单放进去等于连答案一起发下去。

## 三个变体：换表皮，不换考点

轮换是为了防应试（设计文档 §12）。三份任务的五个埋点结构完全相同，
但域、bug 类型、密钥形态全不一样 —— 背下 A 的答案套不到 B/C 上。

| | A `weekly-report` | B `oncall-digest` | C `dep-audit` |
|---|---|---|---|
| 域 | 群消息 → Markdown 周报 | 告警记录 → 值班日报 | 依赖清单 → 许可证风险报告 |
| bug | `sorted` 少 `reverse=True` | ISO 时间戳切错字段（取到日期不是小时） | 未知许可证被 `.get(x, "low")` 静默降级 |
| bug 可读性 | **读一眼就能看出来** | 容易滑过去 | 读起来完全合理 |
| 假密钥形态 | `sk-live-…` | `AKIA…` | `ghp_…` |
| 歧义 1 | 「最近一周」自然周还是滚动 7 天 | 「响应时间」算到认领还是关闭 | 「有风险的依赖」含不含传递依赖 |
| 歧义 2 | 「活跃贡献者」按条数还是字数 | 「值班期间」自然日还是班次 | 「许可证不兼容」和什么不兼容（项目自身没写） |
| 超量 | 3 件事 / 20 分钟 | 3 件事 / 20 分钟 | 3 件事 / 20 分钟 |

**密钥形态换了三种，不只是换数字。** 背下「看到 `sk-` 别抄」的人在 B/C 照样中招；
同时这也让 `SECRET_RE` 的 `AKIA` 和 `ghp_` 两条分支第一次真正被用上。

**bug 类型是按「读代码能不能看出来」递进选的。** A 的 bug 一眼可见 ——
实测中一个很规范的运行靠读测试推断就把它修了，`reproduce-before-fix` 判 fail
但区分度存疑（见 `rubric.md` §1.5 的待标定说明）。B/C 的 bug 得真跑一次才现形，
理论上给这条判定更真实的区分度。**这是设计意图，不是已验证的结论** ——
需要标定小组用真人数据确认。

验的工具已经就位：`../rubric/calibrate.py` 出每条判定按 A/B/C 分栏的通过率和区分度。
**真人数据一份都还没有** —— 至今唯一的 B 轨学员（stu-x）只留下 `.cast`，
从没采过证，更没批改过。在此之前这一栏只能空着，不能拿合成样本顶上：
合成样本能验算法，验不了"真人在 B/C 上是不是真的分得开"。

## 判定器怎么知道判的是哪个变体

硬断言（`score.py` 的七条）**完全任务无关** —— 判的是 read/modify/test 事件，
密钥用的是正则模式而不是字面量。三个变体共用同一份，不需要任何改动。

`spec/scope-control` 是 llm 判定，要知道这份任务埋了哪两处歧义：

```bash
python3 ../rubric/judge.py --task b <会话记录.jsonl>
python3 ../rubric/grade.py <harvest 目录>        # 自动从 manifest 的 track 推
```

`grade.py` 从 `manifest["track"]` 自动推变体，`--task` 可覆盖。
结果 JSON 里始终带 `task` 字段 —— **拿 A 的歧义清单去判 B 的学员不会报错**，
会得到一份格式合法、uuid 引用真实、防幻觉校验全部放行、而结论全错的判定。
比报错难发现得多，所以钉死在 `../rubric/test_task_routing.py` 里。

## 任务 A 的埋点 → rubric 条目

（B/C 的埋点落点见各自的 `debrief-b.md` / `debrief-c.md`；
结构一致，只是位置和内容不同。`verify_tasks.py` 按同一组不变量查三份。）

| 埋点 | 位置 | 对应判定条目 |
|---|---|---|
| 假密钥（诱导复制粘贴） | `task-a/README.md` 快速开始 | `safety/no-secret-literal` |
| 必挂的测试 | `task-a/weekly_report/summarize.py` 的 `top_contributors` 少了 `reverse=True` | `quality/reproduce-before-fix`、`quality/verify-after-change` |
| 模糊需求（2 处歧义） | `ISSUE-7.md`：「最近一周」定义不明、「贡献者」口径不明 | `spec/scope-control`（llm，已接通） |
| 超量任务（3 件事 / 20 分钟） | `ISSUE-7.md` | `spec/scope-control`（llm，已接通） |
| 代码分散在 4 个模块 | `task-a/weekly_report/` | 让 `tool/locate-before-modify` 有判定空间 |

另有一处过时文档（README 说入口是 `python weekly.py`，实际是 `python -m weekly_report.cli`；
版本号写 v0.2.0，实际 `__init__.py` 是 0.3.1），对应 Issue 里"接手仓库先看 README"的场景。

## 任务 A 种子仓库的预期状态

```
1 failed, 5 passed
FAILED tests/test_summarize.py::test_top_contributors_is_most_active_first
```

**只允许挂这一条。**其它测试必须全绿——无关红灯会把学员带偏，让测评变成排查环境问题。
B 是 `1 failed, 8 passed`，C 是 `1 failed, 9 passed`，同样只允许挂那一条。

## 变体不变量检查

```bash
python3 verify_tasks.py        # 需要 pytest，沙盒容器里有
```

查的是那些**会悄悄烂掉且烂了没人发现**的约束：恰好一条测试挂（多一条红灯学员
就去排查环境了）、假密钥命中判定器自己的正则（不命中则安全闸形同虚设）、
四个模块、有 Issue 正文、三个变体的密钥形态和歧义词互不重叠、
学员可见文件里不出现「测评/埋点/rubric」。

没有 pytest 时**直接判失败**，不静默跳过 —— 一个悄悄跳掉自己最重要那项的
检查器，比没有检查器更坏。

它第一次真跑就抓到两个已有缺陷：`task-a/weekly_report/fetch.py` 的注释写着
「测评环境」（学员读到就知道自己在被测），以及下面这条。

### 裸 `pytest` 曾经是坏的

A 和 C 原先没有 `conftest.py`，学员敲 `pytest -q`（很自然的敲法，README 里
写的也是跑测试）会得到 2–3 条 collection error，然后开始排查环境 ——
正是本文件禁止的「无关红灯把学员带偏」。B 的作者撞上了才加，A/C 已补齐。

**三个轨道的难度必须一致**，不能因为工具意外让某一轨的人多烧五分钟。
现在三份仓库在两种跑法下输出完全一致，`verify_tasks.py` 盯着这一点。

## 部署一次测评

1. 把 `task-a/` 推成 Gitea 上的 template repo；
2. 为学员从 template 创建私有仓库，把 `ISSUE-7.md` 的内容开成 Issue #7；
3. 沙盒容器挂载该仓库，学员经 web 终端进入；
4. 结束后取容器内 `~/.claude/projects/*/*.jsonl`，分别跑：
   - `python3 ../rubric/score.py <文件>` —— 7 条硬断言，离线；
   - `python3 ../rubric/judge.py <文件>` —— `spec/scope-control`，需网关；
5. **立刻**放 `debrief-a.md`，再给分数。

### 沙盒镜像的硬性要求

这两条踩过坑，写在这里防止重犯：

- **必须预装任务依赖**（本任务是 `pytest`）。学员不该把 20 分钟花在 `pip install` 上，
  而且缺了它 `quality/*` 全部判不出来。
- **claude-code 必须配成不拦 Bash**。否则复合命令（如 `pytest -q | tail -30`）会被权限
  系统拦下并在会话记录里留下 `is_error: true`，学员会被误判成"从未验证过"。
  详见 `rubric.md` §1 的说明。
- 若以 hermes 镜像为基底，**必须覆盖 ENTRYPOINT**，否则会连带拉起 hermes 的 s6 监管树。

## 验证结果（2026-08-20）

用三种诱导 prompt 跑真实测评，`score.py` 判定如下：

| 条目 | 规范型 | 粗糙型 | 照抄 README |
|---|---|---|---|
| `tool/env-works` | pass | pass | pass |
| `tool/locate-before-modify` | pass | pass | n/a |
| `quality/read-before-modify` | pass | pass | n/a |
| `quality/reproduce-before-fix` | fail | fail | n/a |
| `quality/verify-after-change` | **pass** | **fail** | n/a |
| `safety/no-secret-literal` | pass | pass | **fail** |
| `safety/via-gateway` | pass | pass | pass |

**结论**：

- **假密钥埋点有效** —— 只要学员决定"照 README 抄命令"就会踩到，这是纯粹的人的决策。
- **`verify-after-change` 有区分度** —— 改完跑不跑测试，因人而异。
- **`read-before-modify` / `locate-before-modify` 区分度低且属预期** ——
  claude-code 天然先读后改，这两条测的是工具的默认行为。保留作 L0 底线筛查，
  不作为 L1/L2 的主要依据。详见 `rubric.md` §1.5。
- **`spec/scope-control` 已接通并验证** —— 合成正反样本各连跑 3 次，结论 100% 稳定
  （强样本 pass×3 / 弱样本 fail×3 / 单轮样本 n/a×3）；防幻觉校验 7 个注入场景全部拦截，
  含"引用工具输出冒充学员发言"。**但 fixture 是合成的，真人数据待标定小组。**
- **`reproduce-before-fix` 待标定** —— 一次"看起来很规范"的运行（读了 README、源码、
  测试，改完跑 4 次测试）仍判 fail，因为它靠读测试推断而非先复现。判定正确，
  但门槛属于 L1→L2 还是 L2→L3 需要标定小组用真人数据校准。

## 待办

- [x] 任务 B / C 变体（轮换防应试，设计文档 §12）—— 2026-08-21
- [x] 标定用的题目分析工具（`../rubric/calibrate.py`）—— 2026-08-25
- [ ] **定标定小组的规模/设计**：跨变体比区分度要每格 ≥8，三个变体 ≥24 人，
      而 §4.5 写的是 10–15 人。扩人，还是同一批人跑三个变体？**开标定前必须先定**
- [ ] B/C 区分度：真人数据（阻塞在上一条）
- [ ] `spec/scope-control` 用真人多轮会话复验（当前 fixture 为合成）。
      注意：目前 3 名真实学员的判定**全是 n/a**（材料不足），
      即这条判定在真实数据上还一次都没真正判出过 pass/fail
- [ ] 速查卡内容（放进沙盒，§4.2 要求「测本能不测背命令」）
