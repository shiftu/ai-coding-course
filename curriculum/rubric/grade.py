#!/usr/bin/env python3
"""批改 agent 的本体：把 rubric 逐条判定聚合成四维向量 + S1 + debrief。

    python3 grade.py <harvest 目录>          # 正常批改一份
    python3 grade.py --transcript <x.jsonl>  # 只有会话记录时也能用
    python3 grade.py --no-llm ...            # 跳过需求表达（离线）

维度和等级边**不在这里硬编码** —— 从 rubric.md 每条的
"**维度** X · **等级边** L1→L2" 那行读出来。改 rubric 就改了批改逻辑，
两处不会漂（设计文档 §4.4：改 rubric = 改一个 markdown）。
"""
import argparse
import json
import os
import re
import subprocess
import time
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import score  # noqa: E402

RUBRIC = os.path.join(HERE, "rubric.md")

# 设计文档 §3.1 的四维。顺序即雷达图顺序。
DIMENSIONS = ("工具操作", "需求表达", "质量验证", "自动化编排")
SAFETY_DIM = "safety-gate"
UNMEASURED = "未测得"
PENDING = "待补测"
LEVELS = ("L0", "L1", "L2")

# "- **维度** 工具操作 · **等级边** L1→L2 · **判定** hard"
META_RE = re.compile(
    r"\*\*维度\*\*\s*(?P<dim>[^\s·]+)"
    r"(?:\s*·\s*\*\*等级边\*\*\s*(?P<edge>L\d\s*[-–—>→]+\s*L\d))?"
    r"\s*·\s*\*\*判定\*\*\s*(?P<kind>hard|llm)")
EDGE_RE = re.compile(r"(L\d)\s*[-–—>→]+\s*(L\d)")


def parse_meta(path=RUBRIC):
    """读出每条判定的 id → {维度, 等级边, 判定类型}。"""
    meta, cur = {}, None
    for line in open(path, encoding="utf-8"):
        h = re.match(r"###\s+(\S+)\s*$", line)
        if h:
            cur = h.group(1)
            continue
        if cur is None:
            continue
        m = META_RE.search(line)
        if m:
            edge = None
            if m.group("edge"):
                e = EDGE_RE.search(m.group("edge"))
                edge = (e.group(1), e.group(2)) if e else None
            meta[cur] = {"dimension": m.group("dim"), "edge": edge, "kind": m.group("kind")}
            cur = None
    if not meta:
        raise RuntimeError(f"{path} 里一条判定元信息都没解析出来——格式变了？")
    return meta


def _edge_state(verdicts, items):
    """一条等级边的状态：crossed / blocked / unmeasured。

    **空集不算通过**：这条边上的条目如果全是 n/a，说明这次任务里没出现
    可判定的场景，既不能判过也不能判没过 —— 只能是 unmeasured。
    这是整个聚合里最容易写错的一处（rubric §0 明确 n/a 不进分子也不进分母）。
    """
    seen = [verdicts[i] for i in items if i in verdicts]
    judged = [v for v in seen if v in ("pass", "fail")]
    if not judged:
        return "unmeasured"
    return "crossed" if all(v == "pass" for v in judged) else "blocked"


def dimension_level(verdicts, meta, dim):
    """一个维度的等级：从 L0 起沿等级边逐级往上走，遇到走不动就停。

    **没有判定条目的边 = 未测得，不能跳过。** 一条边上没条目，说明本次测评
    根本没测这一级的行为；直接跳到下一条边去判，等于凭空替学员认领了一级。
    需求表达就是这种情况：rubric 只实现了 L1→L2，没有 L0→L1 的锚点
    （设计文档 §3.1 里那条"一句话说清任务"没落成条目）。
    这时哪怕 L1→L2 判了 fail，也只能说"上限不超过 L1"，
    **不能说他是 L1**（没测过），更不能说是 L0（那是冤枉人）。
    """
    by_edge = {}
    for item, m in meta.items():
        if m["dimension"] != dim or not m["edge"]:
            continue
        by_edge.setdefault(m["edge"], []).append(item)
    if not by_edge:
        return {"level": UNMEASURED, "edges": {}, "upper_bound": None,
                "reason": "本次测评没有这一维的判定条目"}

    # 先把每条边的状态都算出来（便于证据页逐条展示），再据此往上走
    edges = {}
    for i in range(len(LEVELS) - 1):
        edge = (LEVELS[i], LEVELS[i + 1])
        items = by_edge.get(edge)
        edges[f"{edge[0]}→{edge[1]}"] = {
            "state": _edge_state(verdicts, items) if items else "no-item",
            "items": sorted(items or []),
        }

    # 阶梯语义有个不对称，写错了就会冤枉人或者白送等级：
    #
    #   过了高的一级 → 低的自然也过（能收窄范围的人，不可能说不清一句话）。
    #     所以**只要有一条边判过**，等级就取它，不管更低的那条测没测。
    #   没过 / 没测到 → **不能反推低的那级**。
    #     "没升到 L2" ≠ "就是 L1" —— 除非 L0→L1 那一级真的判过。
    #
    # 需求表达正好是后一种：rubric 只实现了 L1→L2，
    # 设计文档 §3.1 里那条 L1 锚点（"一句话说清任务"）还没落成条目。
    # 这时 spec/scope-control 判 fail，只能得出"上限不超过 L1"，
    # 下限未知 —— 既不能说他是 L1，也不能说是 L0。
    keys = [f"{LEVELS[i]}→{LEVELS[i + 1]}" for i in range(len(LEVELS) - 1)]

    crossed_at = None
    for i, k in enumerate(keys):
        if edges[k]["state"] == "crossed":
            crossed_at = i
    if crossed_at is not None:
        level = LEVELS[crossed_at + 1]
        nxt = keys[crossed_at + 1] if crossed_at + 1 < len(keys) else None
        st = edges[nxt]["state"] if nxt else None
        reason = {"blocked": f"{nxt} 有条目未通过",
                  "unmeasured": f"{nxt} 本次未测得",
                  "no-item": f"{nxt} 没有判定条目——本次测不出这一级"}.get(st)
        return {"level": level, "edges": edges,
                "upper_bound": level if st == "blocked" else None, "reason": reason}

    # 一条都没过。只有当**最低那条边本身判了 fail** 时，才谈得上 L0 ——
    # 那是实打实没站稳第一级。否则就是没测到。
    first = keys[0]
    if edges[first]["state"] == "blocked":
        return {"level": LEVELS[0], "edges": edges, "upper_bound": LEVELS[0],
                "reason": f"{first} 有条目未通过"}

    blocked = next((k for k in keys if edges[k]["state"] == "blocked"), None)
    if blocked:
        i = keys.index(blocked)
        return {"level": UNMEASURED, "edges": edges, "upper_bound": LEVELS[i],
                "reason": f"{blocked} 未通过，但 {first} 没判过——上限 {LEVELS[i]}，下限未知"}
    return {"level": UNMEASURED, "edges": edges, "upper_bound": None,
            "reason": f"{first} " + ("没有判定条目" if edges[first]["state"] == "no-item"
                                     else "本次未测得")}


def s1_result(verdicts, meta):
    items = [i for i, m in meta.items() if m["dimension"] == SAFETY_DIM]
    seen = [verdicts[i] for i in items if i in verdicts]
    judged = [v for v in seen if v in ("pass", "fail")]
    if not judged:
        return "unmeasured", sorted(items)
    failed = sorted(i for i in items if verdicts.get(i) == "fail")
    return ("fail" if failed else "pass"), failed


def aggregate(verdicts, meta=None):
    """四维向量 + S1 + 总等级。"""
    meta = meta or parse_meta()
    dims = {d: dimension_level(verdicts, meta, d) for d in DIMENSIONS}
    s1, s1_detail = s1_result(verdicts, meta)

    measured = {d: v["level"] for d, v in dims.items() if v["level"] != UNMEASURED}
    holes = [d for d, v in dims.items() if v["level"] == UNMEASURED]

    # 短板决定制（设计文档 §3.3）——但**有洞的向量不能取 min**。
    # 除非已测得的维度里已经出现 L0：那已经是最低了，补测不可能让它更低，
    # 结论可以当场下，不必让学员干等。
    if not measured:
        overall = PENDING
    elif LEVELS[0] in measured.values():
        overall = LEVELS[0]
    elif holes:
        overall = PENDING
    else:
        overall = min(measured.values(), key=LEVELS.index)

    # S1 是资格闸不是分数：不改任何一维的等级，只封顶总等级（§3.2）。
    capped = bool(s1 == "fail" and overall in ("L2",))
    if capped:
        overall = "L1"

    return {
        "dimensions": dims,
        "s1": s1,
        "s1_failed_items": s1_detail if s1 == "fail" else [],
        "overall": overall,
        "unmeasured_dimensions": holes,
        "capped_by_s1": bool(s1 == "fail"),
    }


# ---- 证据定位 -------------------------------------------------------------

def evidence_links(transcript, results):
    """把 score.py 给的 evidence_seq 换成人能核对的位置。

    证据不是"相信我"，是"你自己去第几行看"。行号 + 工具名 + 命令片段，
    学员拿着 rubric.md 的断言块可以自己复算（rubric §7 申诉）。
    """
    tool_uses, _ = score.load_events(transcript)
    by_seq = {t["seq"]: t for t in tool_uses}
    out = {}
    for item, r in results.items():
        refs = []
        for seq in r.get("evidence_seq", []):
            t = by_seq.get(seq)
            if not t:
                continue
            refs.append({
                "seq": seq, "tool": t["name"], "uuid": t["uuid"],
                "excerpt": t["raw"][:160],
            })
        out[item] = refs
    return out


# ---- debrief ---------------------------------------------------------------

TRAP_HINTS = {
    "safety/no-secret-literal":
        "任务仓库 README 里预埋了一个假密钥，就在你改过的那段代码块里。"
        "埋点是故意的——问题不是你有没有看见它，是你**手指头划过那一行时**有没有停一下。",
    "quality/reproduce-before-fix":
        "Issue 说测试挂了。先跑一次看它怎么挂，和读代码推断它为什么挂，"
        "是两件事——前者会告诉你真实报错，后者只会告诉你你以为的报错。",
    "quality/verify-after-change":
        "改完跑一遍测试再说完成。这是 L1 的底线，不是加分项。",
    "spec/scope-control":
        "任务量是故意略超时长的。20 分钟做不完三件事——"
        "主动说清「这次先做哪部分、哪部分留着」，比闷头做到超时更专业。",
}

# 说明文案只在 reason 为空时兜底。不要在这里写维度特定的话
# （"会收窄范围"是需求表达的锚点，套到工具操作头上就成了胡说）。
LEVEL_TEXT = {
    "L0": "第一级的行为锚点没通过",
    "L1": "过了 L0→L1",
    "L2": "本次可测的判定全部通过",
    UNMEASURED: "本次没测到",
    PENDING: "等补测",
}


def debrief(student, agg, results, links, manifest=None):
    """给学员看的复盘文本。测评即第一课（设计文档 §4.2）。"""
    L = []
    a = L.append
    a(f"# {student} · 测评复盘\n")
    a("> 判定规则全文在 `rubric/rubric.md`，每条都附了你会话记录里的位置。")
    a("> 不认同任何一条都可以申诉——人工会调你的完整记录和录屏复核。\n")

    a("## 你的四维\n")
    a("| 维度 | 等级 | 说明 |")
    a("|---|---|---|")
    for dim in DIMENSIONS:
        d = agg["dimensions"][dim]
        note = d.get("reason") or LEVEL_TEXT.get(d["level"], "")
        if d.get("upper_bound") and d["level"] == UNMEASURED:
            note = f"上限 {d['upper_bound']}，下限未测——{note}"
        a(f"| {dim} | **{d['level']}** | {note} |")
    a("")

    s1 = agg["s1"]
    a(f"## S1 安全闸：{'通过' if s1 == 'pass' else '未通过' if s1 == 'fail' else '未测得'}\n")
    if s1 == "fail":
        a("未通过意味着暂不解锁 L2 内容。踩到的是：")
        for it in agg["s1_failed_items"]:
            a(f"- `{it}`")
        a("")

    if agg.get("blank_submission"):
        a("## ⚠ 本次没有任何修改或测试动作\n")
        a("整场会话里没有出现改文件、也没有跑测试。质量类判定全部判 n/a"
          "（没发生的场景不能判），所以雷达图上是「未测得」而不是低分——"
          "**但这不代表通过**。总等级会记待补测，并会进人工抽查。\n")

    a(f"## 总等级：{agg['overall']}\n")
    if agg["overall"] == PENDING:
        a("四维里还有没测到的（" + "、".join(agg["unmeasured_dimensions"]) + "），"
          "短板决定制要求四维齐全才能定级——**有洞的向量不能取最小值**，"
          "所以先记待补测，由后续作业补上。")
    elif agg["capped_by_s1"]:
        a("S1 未过，总等级封顶 L1。安全闸是资格闸不是扣分项——"
          "补过闸之后等级按四维重算。")
    if agg["capped_by_s1"] and agg["overall"] == PENDING:
        # 待补测那一支已经打印过了，但 S1 这件事不能因此被吞掉：
        # 补测完成后如果 S1 还没补过，等级仍然会被封在 L1。
        a("\n另外 S1 未过——即使补测完成，总等级也会先封顶在 L1，"
          "直到安全闸补过为止。")
    a("")

    fails = [i for i, r in results.items() if r.get("verdict") == "fail"]
    if fails:
        a("## 埋点揭晓\n")
        a("测评任务里布了几个点，现在全部摊开。踩到的：\n")
        for it in fails:
            a(f"### `{it}`\n")
            if it in TRAP_HINTS:
                a(TRAP_HINTS[it] + "\n")
            for ref in links.get(it, [])[:3]:
                a(f"- 会话第 {ref['seq']} 个工具调用（{ref['tool']}）：`{ref['excerpt'][:100]}`")
            a("")

    nas = [i for i, r in results.items() if r.get("verdict") == "n/a"]
    if nas:
        a("## 本次没判到的\n")
        a("这些条目对应的场景本次任务里没出现，**不计入分子也不计入分母**，不影响等级：\n")
        for it in nas:
            a(f"- `{it}` —— {results[it].get('reason', '本次无可判定场景')}")
        a("")

    if manifest and manifest.get("empty_sources"):
        a("## ⚠ 采证有缺口\n")
        a("这几路证据是空的：" + "、".join(manifest["empty_sources"]) + "。")
        a("**空证据不等于你没做**——先查采集本身有没有坏，再看判定。"
          "如果你确实做了而证据没采到，请在申诉里说明。\n")
    return "\n".join(L)


# ---- 驱动 -----------------------------------------------------------------

def all_transcripts(harvest_dir):
    """harvest 里的**全部**会话记录，按最早时间戳排序。

    **不能只取一份。** 学员一场测评里通常有多个会话：/clear 之后重开、
    `claude -p` 顺手问一句、断线后 --continue。原来的实现取"最大的那份"，
    是个静默的任意选择，两个方向都会错：

      - 漏证据：在会话 A 里读了文件、在会话 B 里改的，
        "先读后改"会因为只看到 B 而误判 fail；
      - 选错场：随手问一句的短会话如果碰巧最大，判的就不是那份作业。

    rubric 问的是"这段时间里你有没有做过 X、顺序如何"，
    所以正确语义是**把整个测评窗口的会话按时间接起来**看。
    """
    root = os.path.join(harvest_dir, "transcripts")
    found = []
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".jsonl"):
                continue
            path = os.path.join(dirpath, f)
            ts = ""
            try:
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        ts = json.loads(line).get("timestamp", "") or ""
                        break
            except (OSError, json.JSONDecodeError):
                pass
            found.append((ts, path))
    return [p for _, p in sorted(found)]


def merge_transcripts(paths, workdir):
    """按时间顺序接成一份，交给打分器。

    序号（evidence_seq）跟着拼接顺序走，正是顺序类断言需要的。
    """
    if len(paths) == 1:
        return paths[0]
    out = os.path.join(workdir, "merged-transcript.jsonl")
    with open(out, "w", encoding="utf-8") as w:
        for p in paths:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        w.write(line if line.endswith("\n") else line + "\n")
    return out


def find_transcript(harvest_dir):
    """兼容旧调用：只要第一份。新代码请用 all_transcripts()。"""
    t = all_transcripts(harvest_dir)
    return t[0] if t else None


def run(transcript, *, use_llm=True, manifest=None, student="学员", task=None):
    # 判哪个变体：优先显式传入，否则从 manifest 的 track 推。track 来自学员档案，
    # 是权威源 —— 靠人每次记得敲 --task，迟早会有人拿 A 的歧义清单去判 B 的学员，
    # 而那种判定是「格式合法、引用真实、结论全错」，最难发现。
    if not task:
        track = (manifest or {}).get("track") or "a"
        task = str(track).lower()
    meta = parse_meta()
    # 直接调 score.score()，不 fork 子进程 —— 同一份代码，不会两处漂。
    # （注意 score 模块里 `evaluate` 是求单条断言的，不是入口。）
    results, _sets = score.score(transcript)

    if use_llm:
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "judge.py"),
             "--task", task, transcript],
            capture_output=True, text=True)
        if out.returncode == 0:
            try:
                results["spec/scope-control"] = json.loads(out.stdout)
            except json.JSONDecodeError:
                results["spec/scope-control"] = {
                    "verdict": "n/a", "guard": "bad-json",
                    "reason": "judge 返回不是 JSON"}
        else:
            # 判不了就判不了，**绝不猜**。n/a 不进分子也不进分母。
            results["spec/scope-control"] = {
                "verdict": "n/a", "guard": "call-failed",
                "reason": f"judge 调用失败：{out.stderr.strip()[:200]}"}

    # --no-llm 时 llm 条目是**故意**没判的，要显式记成 skipped，
    # 否则下面的漂移告警会把它当成 bug 报出来 —— 狼来了喊多了就没人看了。
    if not use_llm:
        for item, m in meta.items():
            if m["kind"] == "llm" and item not in results:
                results[item] = {"verdict": "n/a", "guard": "skipped-no-llm",
                                 "reason": "本次以 --no-llm 运行，llm 条目未判定"}

    verdicts = {k: v.get("verdict") for k, v in results.items()}

    # 到这儿还缺的，才是真的不同步：rubric.md 里写了这条，打分器却没产出结果。
    # 这是代码 bug，必须显性化，不能让它悄悄变成"这一维没测到"。
    missing = sorted(set(meta) - set(verdicts))
    for m in missing:
        results[m] = {"verdict": "n/a", "guard": "not-evaluated",
                      "reason": "rubric 里有这条，但打分器没产出结果——两者不同步"}
        verdicts[m] = "n/a"

    agg = aggregate(verdicts, meta)
    links = evidence_links(transcript, results)

    # 交白卷检测。
    #
    # 现在的 rubric 没有一条判"你到底动手了没有" —— 所有质量类条目都带
    # `require: modify`，一行没改就全判 n/a，于是四维显示"未测得"而不是 L0。
    # 这在逻辑上是对的（没发生的场景不能判），但留下一个应试口子：
    # **什么都不做，就什么都判不了。**
    #
    # 这里不擅自加判定条目（加哪一条、算在哪条等级边上，是标定小组的活，
    # 见设计文档 §4.5），只把事实显性标出来，让人工抽查一眼看见。
    _, sets = score.score(transcript)
    attempted = bool(sets.get("modify")) or bool(sets.get("test"))
    if not attempted:
        agg["blank_submission"] = True
    return {
        "student": student,
        "graded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # 判的是哪个变体，落在顶层。
        # 以前它只活在 results["spec/scope-control"]["task"] 里 —— 那是 judge 的返回体，
        # --no-llm 或 judge 调用失败时整条被换成兜底 dict，变体标签跟着一起没了。
        # 标定小组要的是「A/B/C 各自的通过率」，手里却是一摞认不出变体的 grade.json，
        # 只能回去翻 manifest.json（还得指望它没被和 grade.json 分开搬走）。
        # 一份判定结果必须自己说得清判的是哪份题。
        "task": task,
        "transcript": transcript,
        "rubric_items_missing": missing,
        "results": results,
        "evidence": links,
        **agg,
        "debrief": debrief(student, agg, results, links, manifest),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("harvest", nargs="?", help="harvest 目录")
    p.add_argument("--transcript", help="直接给一份会话记录")
    p.add_argument("--student", default=None)
    p.add_argument("--task", default=None,
                   help="按哪个变体的歧义清单判（a/b/c）。默认从 manifest 的 track 推")
    p.add_argument("--no-llm", action="store_true", help="跳过需求表达（离线）")
    p.add_argument("--json", action="store_true", help="输出完整 JSON 而不是 debrief")
    p.add_argument("--out", help="把 debrief 和 JSON 写到这个目录")
    a = p.parse_args()

    # 输出目录要先建：合并后的会话记录就落在这里，
    # merge 之前不建，--out 指向新目录时会 FileNotFoundError。
    if a.out:
        os.makedirs(a.out, exist_ok=True)

    manifest, student = None, a.student
    transcript, sessions = a.transcript, ([a.transcript] if a.transcript else [])
    if a.harvest and not a.transcript:
        mpath = os.path.join(a.harvest, "manifest.json")
        if os.path.exists(mpath):
            manifest = json.load(open(mpath))
            student = student or manifest.get("student")
        sessions = all_transcripts(a.harvest)
        if sessions:
            # 整个测评窗口的会话一起判（见 all_transcripts 的说明）
            transcript = merge_transcripts(sessions, a.out or a.harvest)
    if not transcript:
        p.error("没找到会话记录：给 harvest 目录或 --transcript")

    r = run(transcript, use_llm=not a.no_llm, manifest=manifest, task=a.task,
            student=student or "学员")
    r["sessions"] = sessions
    r["session_count"] = len(sessions)

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "grade.json"), "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        with open(os.path.join(a.out, "debrief.md"), "w") as f:
            f.write(r["debrief"] + "\n")
        print(f"写到 {a.out}/grade.json 与 debrief.md")

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif not a.out:
        print(r["debrief"])


if __name__ == "__main__":
    main()
