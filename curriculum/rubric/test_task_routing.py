#!/usr/bin/env python3
"""任务变体路由的离线测试。

盯的是一类**看不见的**失败：拿任务 A 的歧义清单去判轨道 B 的学员。
模型会照着「最近一周」「活跃贡献者」去找，而 B 的 Issue 里没有这两个词，
于是稳定判 fail —— 判定格式合法、uuid 引用真实、理由通顺，
所有防幻觉校验全部放行。这种错比报错难发现得多，所以钉死在测试里。

    python3 test_task_routing.py        # 不打网络
"""
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
fails = []


def check(name, cond, detail=""):
    print(f"  [{'  ok ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, HERE / f"{mod}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


judge = _load("judge")

print("\n范围规格文件")
scopes = {}
for t in ("a", "b", "c"):
    try:
        scopes[t] = judge.load_scope(t)
        ok = True
    except SystemExit:
        ok = False
    check(f"scope/{t}.json 存在且可解析", ok)

for t, sc in scopes.items():
    check(f"{t}: 恰好 2 处歧义", len(sc.get("ambiguities", [])) == 2,
          f"实得 {len(sc.get('ambiguities', []))}")
    check(f"{t}: 每处歧义都有 issue_line 和 criterion",
          all(a.get("issue_line") and a.get("criterion") for a in sc["ambiguities"]))
    check(f"{t}: 有 overload_line", bool(sc.get("overload_line")))

print("\n变体之间不能串味")
terms = {t: {a["term"] for a in sc["ambiguities"]} for t, sc in scopes.items()}
for x in ("a", "b", "c"):
    for y in ("a", "b", "c"):
        if x < y:
            check(f"{x} / {y} 的歧义词不重叠", not (terms[x] & terms[y]),
                  f"重叠：{terms[x] & terms[y]}" if terms[x] & terms[y] else "")

print("\n任务 A 的 prompt 未被改动（参数化不能改变既有判定）")
want = (HERE / "fixtures" / "prompt-a.expected.txt").read_text(encoding="utf-8")
got = judge.PROMPT.format(task_block=judge.render_task_block(scopes["a"]), turns="<<TURNS>>")
check("逐字节一致", got == want,
      "" if got == want else "prompt 变了 —— A 的历史判定不再可复现")

print("\n未知变体必须炸，不能静默回退到 A")
try:
    judge.load_scope("nope")
    check("load_scope('nope') 抛错", False, "它返回了，等于静默按 A 判")
except SystemExit:
    check("load_scope('nope') 抛错", True)

print("\ngrade.py 从 manifest 的 track 推变体")
grade = _load("grade")
seen = {}


def fake_run(cmd, **kw):
    seen["cmd"] = cmd
    class R:
        returncode = 0
        stdout = json.dumps({"task": cmd[cmd.index("--task") + 1],
                             "verdict": "n/a", "evidence": [], "guard": "stub"})
        stderr = ""
    return R()


grade.subprocess.run = fake_run
t = str(HERE / "fixtures" / "good-run.jsonl")
for track, want_task in (("B", "b"), ("C", "c"), ("A", "a"), (None, "a")):
    seen.clear()
    out = grade.run(t, use_llm=True, manifest={"track": track}, student="x")
    got_task = seen["cmd"][seen["cmd"].index("--task") + 1]
    check(f"track={track!r} → --task {want_task}", got_task == want_task, f"实得 {got_task}")
    # 顶层 task：标定小组手里是一摞 grade.json，得靠它认出谁做的是哪份题。
    check(f"track={track!r} → grade.json 顶层 task={want_task}",
          out.get("task") == want_task, f"实得 {out.get('task')!r}")

# --no-llm 时 judge 整条不跑，变体标签只能靠顶层这一份 ——
# 它以前藏在 judge 的返回体里，--no-llm 一开就整个消失。
out = grade.run(t, use_llm=False, manifest={"track": "C"}, student="x")
check("--no-llm 时顶层 task 仍在", out.get("task") == "c", f"实得 {out.get('task')!r}")

seen.clear()
grade.run(t, use_llm=True, manifest={"track": "A"}, task="c", student="x")
check("显式 --task 覆盖 manifest",
      seen["cmd"][seen["cmd"].index("--task") + 1] == "c")

print(f"\n  {'全部通过' if not fails else str(len(fails)) + ' 项不符：' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
