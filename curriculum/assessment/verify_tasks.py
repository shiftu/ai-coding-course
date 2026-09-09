#!/usr/bin/env python3
"""测评任务变体的不变量检查。

这些约束会悄悄烂掉，且烂了不会有人发现 —— 一份挂了两条测试的种子仓库，
学员会以为环境坏了；一份密钥不匹配判定正则的仓库，safety 闸门形同虚设。

    python3 verify_tasks.py               # 全查（需要 pytest）
    python3 verify_tasks.py --no-pytest   # 显式跳过测试执行

**不给 --no-pytest 而环境里没有 pytest 时直接判失败**，不静默跳过：
一个悄悄跳掉自己最重要那项的检查器，比没有检查器更坏。
"""
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
RUBRIC = HERE.parent / "rubric"
TASKS = sorted(p for p in HERE.glob("task-*") if p.is_dir())
STUDENT_FORBIDDEN = re.compile(r"测评|埋点|rubric", re.I)

fails = []


def check(name, cond, detail=""):
    print(f"  [{'  ok ' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("score", RUBRIC / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

run_pytest = "--no-pytest" not in sys.argv
if run_pytest:
    probe = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        print("\n本环境没有 pytest。要么装上，要么显式 --no-pytest。")
        print("（沙盒容器里有：docker exec mc-<学员> bash -lc '...'）")
        sys.exit(2)

secrets_seen = {}

for t in TASKS:
    tid = t.name.split("-", 1)[1]
    print(f"\n{t.name}")

    pkgs = [d for d in t.iterdir()
            if d.is_dir() and (d / "__init__.py").exists() and d.name != "tests"]
    check(f"{tid}: 恰好一个包", len(pkgs) == 1, f"实得 {[p.name for p in pkgs]}")
    if pkgs:
        mods = [f for f in pkgs[0].glob("*.py") if f.name != "__init__.py"]
        # 4 个模块是硬要求：tool/locate-before-modify 需要判定空间，
        # 一个文件就看全的仓库让这条判定失去意义。
        check(f"{tid}: 4 个模块", len(mods) == 4, f"实得 {len(mods)}：{sorted(m.name for m in mods)}")

    # 假密钥必须命中判定器**自己**的正则，不是另写一个
    for fname in ("README.md", ".env.example"):
        f = t / fname
        m = score.SECRET_RE.search(f.read_text(encoding="utf-8")) if f.exists() else None
        check(f"{tid}: {fname} 命中 SECRET_RE", bool(m), m.group(0) if m else "没有可踩的假密钥")
        if m and fname == "README.md":
            secrets_seen[tid] = m.group(0)

    check(f"{tid}: 有 conftest.py（裸 pytest 也要能跑）", (t / "conftest.py").exists())
    check(f"{tid}: 没有 .git", not (t / ".git").exists())
    check(f"{tid}: 没有 __pycache__", not list(t.rglob("__pycache__")))

    issues = list(HERE.glob(f"ISSUE-{tid.upper()}.md")) + \
             ([HERE / "ISSUE-7.md"] if tid == "a" and (HERE / "ISSUE-7.md").exists() else [])
    check(f"{tid}: 有 Issue 正文", bool(issues), issues[0].name if issues else "学员不知道要做什么")

    check(f"{tid}: 有 scope 规格", (HERE / "scope" / f"{tid}.json").exists())

    # 过时文档埋点：README 写的版本号必须和 __init__ 不一致
    if pkgs:
        real = re.search(r'__version__\s*=\s*"([^"]+)"',
                         (pkgs[0] / "__init__.py").read_text(encoding="utf-8"))
        rm = (t / "README.md").read_text(encoding="utf-8")
        check(f"{tid}: README 版本号和实际不符（过时文档埋点）",
              bool(real) and real.group(1) not in rm,
              f"__init__={real.group(1) if real else '?'}")

    leaked = [f.relative_to(t) for f in t.rglob("*")
              if f.is_file() and f.suffix in (".md", ".py", ".txt")
              and STUDENT_FORBIDDEN.search(f.read_text(encoding="utf-8", errors="ignore"))]
    check(f"{tid}: 学员可见文件不提测评/埋点/rubric", not leaked, str(leaked[:3]) if leaked else "")

    if run_pytest:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                           cwd=t, capture_output=True, text=True)
        tail = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
        m = re.search(r"(\d+) failed,\s*(\d+) passed", tail)
        # **恰好一条挂**。多一条红灯，学员就会去排查环境而不是做题。
        check(f"{tid}: 恰好 1 条测试挂", bool(m) and m.group(1) == "1", tail)
        check(f"{tid}: 至少 5 条测试", bool(m) and int(m.group(1)) + int(m.group(2)) >= 5, tail)

print("\n反作弊：三个变体之间")
check("密钥形态互不相同",
      len({s.split("-")[0][:4] for s in secrets_seen.values()}) == len(secrets_seen),
      str(secrets_seen))
scopes = {p.stem: json.loads(p.read_text(encoding="utf-8"))
          for p in (HERE / "scope").glob("*.json")}
terms = {k: {a["term"] for a in v["ambiguities"]} for k, v in scopes.items()}
for x in sorted(terms):
    for y in sorted(terms):
        if x < y:
            check(f"{x}/{y} 歧义词不重叠", not (terms[x] & terms[y]))

print(f"\n  {'全部通过' if not fails else str(len(fails)) + ' 项不符：' + '; '.join(fails)}")
sys.exit(1 if fails else 0)
