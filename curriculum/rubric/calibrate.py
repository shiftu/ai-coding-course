#!/usr/bin/env python3
"""标定小组的题目分析：把一批批改结果变成每条判定的难度和区分度。

    python3 calibrate.py <批改结果...> [--md] [--json]

    # 一整个学员证据目录（自动挑每人最新的一批批改）
    python3 calibrate.py ~/.local/state/microclass/evidence/*
    # 单份 harvest 目录、单份 grade.json、或裸 transcript（裸的要标变体）
    python3 calibrate.py harvest-2026.../ someone/grade.json run-hasty.jsonl=a

为什么要有它：在这之前，判定只能一份一份看（`score.py <一份>`、`grade.py <一批>`）。
README 里那张"验证结果"表是拿 3 次运行手工拼的。标定小组是 10–15 人 × 三个变体，
手工拼不出来，也就拼不出"区分度"这个数——最后只会拼出印象。

**它不会替你下结论。** 样本不够时只打原始计数，并明说还差多少人。
一个在 n=3 上算出区分度并印出来的工具，比没有工具更坏：
那个数看起来像证据，其实是噪声，而且从此没人再去补样本。
"""
import argparse
import glob
import json
import math
import os
import sys

import score

# 报区分度的最低样本量。低于它只出计数，不出 D / r。
#
# 8 不是从统计功效推出来的精确门槛，是个刻意保守的下限：经典题目分析的
# 27% 分组法在 n=8 时上下组各 2–3 人，已经是「勉强能算」的边缘。
# 真要拿区分度当决策依据，每格 15+ 才谈得上稳。
MIN_N = 8
# 27% 分组法：上下组各取总分排序的前/后 27%，但每组至少 3 人。
UPPER_FRAC = 0.27
MIN_GROUP = 3

SCORED = ("pass", "fail")       # n/a 既不进分子也不进分母


def _load_grade_json(path):
    with open(path) as f:
        d = json.load(f)
    task = d.get("task")
    if not task:
        # 老的 grade.json 没有顶层 task（那是这次才补的）。退而求其次：
        # 先看 judge 返回体里的，再看同级 manifest.json 的 track。
        task = ((d.get("results") or {}).get("spec/scope-control") or {}).get("task")
    if not task:
        mf = os.path.join(os.path.dirname(os.path.dirname(path)), "manifest.json")
        if os.path.isfile(mf):
            with open(mf) as f:
                task = (json.load(f).get("track") or "").lower() or None
    verdicts = {k: (v or {}).get("verdict") for k, v in (d.get("results") or {}).items()}
    return {"label": d.get("student") or os.path.basename(path),
            "task": task, "verdicts": verdicts, "source": path}


def _latest_graded(evidence_dir):
    """一名学员可能被采证批改过多次。取最新的那一批，一人只算一票。

    不取全部——同一个人在结果里出现三次会把他的行为权重放大三倍，
    区分度会被这个人的个人风格带着走。
    """
    cands = sorted(glob.glob(os.path.join(evidence_dir, "harvest-*", "grade", "grade.json")))
    return cands[-1] if cands else None


def collect(paths, default_task=None):
    """把各种形态的输入统一成 [{label, task, verdicts}]。

    认不出来的路径不静默丢掉——原样返回到 skipped 里，让调用方打出来。
    悄悄少几个人的标定结果，比报错难发现得多。
    """
    runs, skipped = [], []
    for raw in paths:
        p, _, tag = raw.partition("=")
        task = (tag or default_task or "").lower() or None

        if os.path.isdir(p):
            g = os.path.join(p, "grade", "grade.json")
            if os.path.isfile(g):
                runs.append(_load_grade_json(g))
                continue
            g = _latest_graded(p)
            if g:
                r = _load_grade_json(g)
                r["label"] = os.path.basename(p.rstrip("/"))
                runs.append(r)
                continue
            skipped.append((p, "目录里没有 harvest-*/grade/grade.json"))
            continue

        if p.endswith(".json"):
            runs.append(_load_grade_json(p))
            continue

        if p.endswith(".jsonl"):
            if not task:
                skipped.append((p, "裸 transcript 认不出变体，用 路径=a 标一下"))
                continue
            res, _ = score.score(p)
            runs.append({"label": os.path.basename(p), "task": task,
                         "verdicts": {k: v.get("verdict") for k, v in res.items()},
                         "source": p})
            continue

        skipped.append((p, "不认识这种输入"))
    return runs, skipped


def _totals(runs, items):
    """每人的总分 = 判 pass 的条数。n/a 不计入，所以还要记各自的可判条数。"""
    out = []
    for r in runs:
        got = [r["verdicts"].get(i) for i in items]
        out.append({"run": r,
                    "score": sum(1 for v in got if v == "pass"),
                    "scored": sum(1 for v in got if v in SCORED)})
    return out


def _discrimination(rows, item):
    """D = 上组通过率 − 下组通过率，按（扣掉本条的）总分分组。

    扣掉本条：只有 7 条判定，拿含本条的总分去分组等于用答案给自己分组，
    每条都会显得很有区分度。这是短测验里最常见的自欺。
    """
    usable = [r for r in rows if r["run"]["verdicts"].get(item) in SCORED]
    if len(usable) < MIN_N:
        return None
    def adj(r):
        return r["score"] - (1 if r["run"]["verdicts"].get(item) == "pass" else 0)
    ranked = sorted(usable, key=adj, reverse=True)
    k = max(MIN_GROUP, round(len(ranked) * UPPER_FRAC))
    if k * 2 > len(ranked):
        k = len(ranked) // 2
    if k < MIN_GROUP:
        return None
    hi, lo = ranked[:k], ranked[-k:]
    ph = sum(1 for r in hi if r["run"]["verdicts"][item] == "pass") / len(hi)
    pl = sum(1 for r in lo if r["run"]["verdicts"][item] == "pass") / len(lo)
    return {"D": round(ph - pl, 3), "p_upper": round(ph, 3), "p_lower": round(pl, 3),
            "group_n": k}


def _point_biserial(rows, item):
    """r_pb，同样用扣掉本条的总分。总分没有方差时返回 None，不返回 0。"""
    usable = [r for r in rows if r["run"]["verdicts"].get(item) in SCORED]
    if len(usable) < MIN_N:
        return None
    adj = [r["score"] - (1 if r["run"]["verdicts"][item] == "pass" else 0) for r in usable]
    ok = [a for a, r in zip(adj, usable) if r["run"]["verdicts"][item] == "pass"]
    no = [a for a, r in zip(adj, usable) if r["run"]["verdicts"][item] == "fail"]
    if not ok or not no:
        return None
    mean = sum(adj) / len(adj)
    var = sum((a - mean) ** 2 for a in adj) / len(adj)
    if var == 0:
        return None            # 所有人总分一样，相关系数无定义。别返回 0 冒充"无相关"
    p = len(ok) / len(adj)
    r = (sum(ok) / len(ok) - sum(no) / len(no)) / math.sqrt(var) * math.sqrt(p * (1 - p))
    return round(r, 3)


def analyse(runs, items):
    rows = _totals(runs, items)
    tasks = sorted({r["task"] or "?" for r in runs})
    out = {"n": len(runs), "n_by_task": {t: sum(1 for r in runs if (r["task"] or "?") == t)
                                         for t in tasks},
           "min_n": MIN_N, "items": {}}

    for item in items:
        per_task = {}
        for t in tasks:
            vs = [r["verdicts"].get(item) for r in runs if (r["task"] or "?") == t]
            sc = [v for v in vs if v in SCORED]
            per_task[t] = {"n_scored": len(sc), "n_na": len(vs) - len(sc),
                           "pass": sum(1 for v in sc if v == "pass"),
                           "p": round(sum(1 for v in sc if v == "pass") / len(sc), 3) if sc else None}

        allv = [r["verdicts"].get(item) for r in runs]
        sc = [v for v in allv if v in SCORED]
        p = round(sum(1 for v in sc if v == "pass") / len(sc), 3) if sc else None

        entry = {"n_scored": len(sc), "n_na": len(allv) - len(sc), "p": p,
                 "by_task": per_task, "discrimination": None, "r_pb": None, "note": None}

        if len(sc) < MIN_N:
            entry["note"] = f"样本不足（可判 {len(sc)}，需要 ≥{MIN_N}）——上面是计数，不是结论"
        elif p in (0.0, 1.0):
            # 全体同判：D 结构上必为 0，但这不代表条目坏了。
            # 底线项本来就该大多数人 pass（rubric §1.5 明说），
            # 把它当"无区分度所以删掉"是误读。
            entry["note"] = ("全体同判（p=%s）——区分度结构上为 0。"
                             "若是底线项属预期；若是区分项，说明门槛设错了边" % p)
        else:
            entry["discrimination"] = _discrimination(rows, item)
            entry["r_pb"] = _point_biserial(rows, item)
        out["items"][item] = entry
    return out


def _fmt(v, dash="—"):
    return dash if v is None else str(v)


def report(a, items):
    L = []
    L.append(f"样本 n={a['n']}    " + "  ".join(f"{t}:{n}" for t, n in a["n_by_task"].items()))
    if a["n"] < MIN_N:
        L.append(f"⚠ 总样本 {a['n']} < {MIN_N}：下面全部只是计数。"
                 f"区分度一个都不会算 —— 这是故意的。")
    L.append("")
    L.append(f"{'条目':<30}{'可判':<6}{'n/a':<6}{'通过率':<8}{'D':<8}{'r_pb':<8}")
    L.append("─" * 66)
    for item in items:
        e = a["items"][item]
        d = e["discrimination"]
        L.append(f"{item:<30}{e['n_scored']:<6}{e['n_na']:<6}{_fmt(e['p']):<8}"
                 f"{_fmt(d and d['D']):<8}{_fmt(e['r_pb']):<8}")
        if e["note"]:
            L.append(f"    {e['note']}")

    L.append("")
    L.append("各变体分开看（标定小组要回答的就是这张表）：")
    tasks = list(a["n_by_task"])
    L.append(f"{'条目':<30}" + "".join(f"{'变体 '+t:<14}" for t in tasks))
    for item in items:
        cells = []
        for t in tasks:
            b = a["items"][item]["by_task"][t]
            cells.append(f"{b['pass']}/{b['n_scored']}" + (f" ({b['p']})" if b["p"] is not None else ""))
        L.append(f"{item:<30}" + "".join(f"{c:<14}" for c in cells))

    short = [t for t, n in a["n_by_task"].items() if n < MIN_N]
    if short:
        L.append("")
        L.append(f"⚠ 变体 {'、'.join(short)} 每格样本 < {MIN_N}，**跨变体比较算不了**。")
        L.append(f"  要按变体比区分度，每个变体各需 ≥{MIN_N} 人 —— 三个变体就是 ≥{MIN_N*3} 人，")
        L.append(f"  而设计文档 §4.5 的标定小组是 10–15 人。两条路选一条：")
        L.append(f"    · 扩到 {MIN_N*3} 人；")
        L.append(f"    · 或让同一批人把三个变体都跑一遍（受试者内设计，样本效率高得多，")
        L.append(f"      代价是第二、三次会带练习效应，得错开顺序）。")
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="+")
    p.add_argument("--task", default=None, help="裸 transcript 的默认变体（a/b/c）")
    p.add_argument("--json", action="store_true", help="出机器可读的 JSON")
    a = p.parse_args()

    runs, skipped = collect(a.paths, a.task)
    for path, why in skipped:
        print(f"跳过 {path} —— {why}", file=sys.stderr)
    if not runs:
        sys.exit("一份批改结果都没读到")

    items = sorted({i for r in runs for i in r["verdicts"]})
    res = analyse(runs, items)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(report(res, items))
    # 样本不够不是错误，是常态；退出码不因此变红。
    return 0


if __name__ == "__main__":
    sys.exit(main())
