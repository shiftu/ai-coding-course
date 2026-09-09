#!/usr/bin/env python3
"""calibrate.py 的统计部分。**这里的数据是合成的，而且只能是合成的** ——

它验的是"算法在已知输入上算得对不对"，不是"B/C 变体有没有区分度"。
后者要真人数据（设计文档 §4.5），任何合成样本都答不了，
把合成结果写进 README 当标定结论，正是这个文件存在要防的事。

    python3 test_calibrate.py
"""
import sys, pathlib
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import calibrate

fails = []
def check(name, ok, extra=""):
    print(f"  [{' ok ' if ok else 'FAIL'}] {name}" + (f"  {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def mk(n, item_verdicts, task="a"):
    """item_verdicts: {条目: [每个人的判定...]}"""
    return [{"label": f"p{i}", "task": task,
             "verdicts": {k: v[i] for k, v in item_verdicts.items()},
             "source": "synthetic"} for i in range(n)]


P, F, NA = "pass", "fail", "n/a"

print("\n样本不足时必须拒绝出区分度")
runs = mk(4, {"x": [P, P, F, F], "y": [P, F, P, F]})
a = calibrate.analyse(runs, ["x", "y"])
check("n=4 < MIN_N：D 为 None", a["items"]["x"]["discrimination"] is None)
check("n=4 < MIN_N：r_pb 为 None", a["items"]["x"]["r_pb"] is None)
check("并且明说是计数不是结论", "不是结论" in (a["items"]["x"]["note"] or ""))

print("\n全体同判：区分度结构上为 0，但要说清是哪种情况")
runs = mk(10, {"x": [P] * 10, "y": [P, F] * 5})
a = calibrate.analyse(runs, ["x", "y"])
check("p=1.0 时 D 不算", a["items"]["x"]["discrimination"] is None)
check("并给出'全体同判'说明", "全体同判" in (a["items"]["x"]["note"] or ""))
check("同一批里 p 在 0/1 之间的条目照常算", a["items"]["y"]["discrimination"] is not None)

print("\n完美区分：高分组全过、低分组全不过 → D=1.0")
# 让 y、z 制造总分梯度，x 与总分完全同向
half = [P] * 5 + [F] * 5
runs = mk(10, {"x": list(half), "y": list(half), "z": list(half)})
a = calibrate.analyse(runs, ["x", "y", "z"])
d = a["items"]["x"]["discrimination"]
check("D = 1.0", d and d["D"] == 1.0, f"实得 {d}")
check("r_pb = 1.0", a["items"]["x"]["r_pb"] == 1.0, f"实得 {a['items']['x']['r_pb']}")

print("\n反向条目：低分组反而更容易过 → D 为负")
runs = mk(10, {"x": [F] * 5 + [P] * 5, "y": list(half), "z": list(half)})
a = calibrate.analyse(runs, ["x", "y", "z"])
d = a["items"]["x"]["discrimination"]
check("D < 0", d and d["D"] < 0, f"实得 {d}")

print("\n总分要扣掉本条，不能拿答案给自己分组")
# 全场只有 x 在变，别的条目所有人一样。
# 扣掉 x 之后总分毫无方差 → r_pb 无定义，必须返回 None。
# 若用的是含 x 的总分，方差 > 0，会算出一个漂亮的 r=1.0 —— 那是自己证明自己。
runs = mk(10, {"x": list(half), "y": [P] * 10, "z": [P] * 10})
a = calibrate.analyse(runs, ["x", "y", "z"])
check("唯一变化源的条目 r_pb 为 None（说明扣了本条）",
      a["items"]["x"]["r_pb"] is None, f"实得 {a['items']['x']['r_pb']}")

print("\nn/a 既不进分子也不进分母")
runs = mk(10, {"x": [P, P, NA, NA, NA, F, F, F, P, P]})
a = calibrate.analyse(runs, ["x"])
e = a["items"]["x"]
check("可判 7", e["n_scored"] == 7, f"实得 {e['n_scored']}")
check("n/a 记 3", e["n_na"] == 3, f"实得 {e['n_na']}")
check("通过率按 4/7 算", e["p"] == round(4 / 7, 3), f"实得 {e['p']}")

print("\n按变体分栏")
runs = mk(4, {"x": [P, P, F, F]}, task="a") + mk(4, {"x": [P, F, F, F]}, task="b")
for i, r in enumerate(runs[4:]):
    r["label"] = f"q{i}"
a = calibrate.analyse(runs, ["x"])
check("a 栏 2/4", a["items"]["x"]["by_task"]["a"]["pass"] == 2)
check("b 栏 1/4", a["items"]["x"]["by_task"]["b"]["pass"] == 1)
check("n_by_task 正确", a["n_by_task"] == {"a": 4, "b": 4}, f"实得 {a['n_by_task']}")

print("\n认不出来的输入必须报出来，不能静默丢掉")
runs, skipped = calibrate.collect(["/nope/whatever.txt", "/nope/run.jsonl"])
check("两个都进了 skipped", len(skipped) == 2, f"实得 {skipped}")
check("裸 transcript 缺变体时说清原因",
      any("认不出变体" in why for _, why in skipped))

print("\n报告在样本不足时挂警告")
runs = mk(3, {"x": [P, F, P]})
txt = calibrate.report(calibrate.analyse(runs, ["x"]), ["x"])
check("总样本不足的警告在", "只是计数" in txt)
check("跨变体比较算不了的提示在", "跨变体比较算不了" in txt)
check("给出了每格所需人数", str(calibrate.MIN_N * 3) in txt)

print(f"\n  {'全部通过' if not fails else str(len(fails)) + ' 项不符：' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
