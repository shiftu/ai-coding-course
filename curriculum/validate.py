#!/usr/bin/env python3
"""校验切片与轨道的一致性。哨兵 cron 与本地自检共用。

不依赖 pyyaml —— 但也不做"尽力猜"的宽松解析：只接受一个明确的 YAML 子集，
任何超出子集的写法都会报错而不是被静默误读。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
SLICES, TRACKS = ROOT / "slices", ROOT / "tracks"
SHOWCASE = ROOT / "showcase"
_CONTROL = ROOT.parent / "platform" / "control"

DIMENSIONS = {"工具操作", "需求表达", "质量验证", "自动化编排", "safety-gate"}
LEVELS = {"L0->L1", "L1->L2", "L2->L3", "S1", "S2", "S3"}
TYPES = {"demo", "exercise", "pitfall", "quiz"}
ENVS = {"container", "own-mac"}
REQUIRED = ("id", "dimension", "level_edge", "type", "env")

errors, warnings = [], []


def err(m):
    errors.append(m)


def warn(m):
    warnings.append(m)


def parse_slice(path):
    """解析 --- 包裹的 frontmatter。只认 `key: value` 与 verify 的固定两行结构。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        err(f"{path}: 缺少 --- frontmatter")
        return None
    meta, verify, in_verify = {}, [], False
    for raw in m.group(1).split("\n"):
        if not raw.strip():
            continue
        if raw == "verify:":
            in_verify = True
            continue
        if in_verify:
            c = re.match(r"^  - cmd: (.+)$", raw)
            e = re.match(r"^    expect_exit: (\d+)$", raw)
            if c:
                verify.append({"cmd": c.group(1).strip().strip('"')})
            elif e and verify:
                verify[-1]["expect_exit"] = int(e.group(1))
            else:
                err(f"{path}: verify 块里无法解析的行 -> {raw!r}")
            continue
        kv = re.match(r"^(\w+): (.+)$", raw)
        if not kv:
            err(f"{path}: 无法解析的 frontmatter 行 -> {raw!r}")
            continue
        meta[kv.group(1)] = kv.group(2).strip()
    meta["verify"] = verify
    return meta


def parse_track(path):
    """只认 `key: value`、`  - id: x`、`      - slice/id` 三种形态。"""
    track, modules, cur, in_slices = {}, [], None, False
    for n, raw in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\w+: ", line):
            k, v = line.split(": ", 1)
            track[k] = v.strip().strip('"')
            in_slices = False
            continue
        if line == "modules:":
            continue
        m = re.match(r"^  - id: (\S+)$", line)
        if m:
            cur = {"id": m.group(1), "slices": []}
            modules.append(cur)
            in_slices = False
            continue
        m = re.match(r"^    (\w+): (.+)$", line)
        if m and cur:
            if m.group(1) == "slices":
                err(f"{path}:{n}: slices 后面不该有值")
            cur[m.group(1)] = m.group(2).strip().strip('"')
            continue
        if line == "    slices:":
            in_slices = True
            continue
        m = re.match(r"^      - (\S+)$", line)
        if m and in_slices and cur:
            cur["slices"].append(m.group(1))
            continue
        err(f"{path}:{n}: 超出允许的 YAML 子集 -> {raw!r}")
    track["modules"] = modules
    return track


def main():
    # ---- 切片 ----
    metas = {}
    for f in sorted(SLICES.rglob("*.md")):
        rel = str(f.relative_to(SLICES))[:-3]
        meta = parse_slice(f)
        if not meta:
            continue
        for k in REQUIRED:
            if k not in meta:
                err(f"{rel}: 缺字段 {k}")
        if meta.get("id") != rel:
            err(f"{rel}: id 字段 {meta.get('id')!r} 与文件路径不一致")
        if meta.get("dimension") not in DIMENSIONS:
            err(f"{rel}: dimension {meta.get('dimension')!r} 不在允许值内")
        if meta.get("level_edge") not in LEVELS:
            err(f"{rel}: level_edge {meta.get('level_edge')!r} 不在允许值内")
        if meta.get("type") not in TYPES:
            err(f"{rel}: type {meta.get('type')!r} 不在允许值内")
        if meta.get("env") not in ENVS:
            err(f"{rel}: env {meta.get('env')!r} 不在允许值内")
        if meta.get("dimension") == "safety-gate" and not meta.get("level_edge", "").startswith("S"):
            err(f"{rel}: safety-gate 切片的 level_edge 必须是 S1/S2/S3")
        for v in meta["verify"]:
            if "expect_exit" not in v:
                err(f"{rel}: verify 项缺 expect_exit")
        metas[rel] = meta

    # ---- 轨道 ----
    referenced = set()
    for f in sorted(TRACKS.glob("track-*.yaml")):
        t = parse_track(f)
        if not t.get("modules"):
            err(f"{f.name}: 没有任何模块")
        seen = set()
        for mod in t["modules"]:
            if not mod["slices"]:
                err(f"{f.name}/{mod['id']}: 模块为空")
            for sid in mod["slices"]:
                if sid not in metas:
                    err(f"{f.name}/{mod['id']}: 引用了不存在的切片 {sid}")
                if sid in seen:
                    err(f"{f.name}: 切片 {sid} 在同一轨道里重复")
                seen.add(sid)
                referenced.add(sid)
        print(f"  {f.name:16} {t.get('name','?'):5} "
              f"{len(t['modules']):>2} 模块 / {len(seen):>2} 切片")

    # ---- 孤儿：没人走的切片就是死内容 ----
    for sid in sorted(set(metas) - referenced):
        warn(f"孤儿切片（没有任何轨道引用）：{sid}")

    # ---- 精选案例：结构规则在 platform/control/showcase.py，这里只跑一遍 ----
    n_cases = check_showcase()

    print(f"\n  切片总数 {len(metas)}，被引用 {len(referenced)}，带机验 "
          f"{sum(1 for m in metas.values() if m['verify'])}，精选案例 {n_cases}")
    for w in warnings:
        print(f"  ⚠ {w}")
    for e in errors:
        print(f"  ✗ {e}")
    print(f"\n  {'校验通过' if not errors else str(len(errors)) + ' 处错误'}")
    return 1 if errors else 0


def check_showcase():
    """curriculum/showcase/<模块>/<verdict-slug>/ 每个案例过一遍 showcase.check_case。

    规则只写在 showcase.py 一处（sandctl showcase 入库时也用它），这里不另抄一份。
    目录不存在 = 还没有案例，不是错。
    """
    if not SHOWCASE.is_dir():
        return 0
    if str(_CONTROL) not in sys.path:
        sys.path.insert(0, str(_CONTROL))
    import showcase  # noqa: E402  平台侧的案例读写器
    known = set(showcase.all_modules())
    n = 0
    for mdir in sorted(p for p in SHOWCASE.iterdir() if p.is_dir()):
        for cdir in sorted(p for p in mdir.iterdir() if p.is_dir()):
            n += 1
            rel = f"showcase/{mdir.name}/{cdir.name}"
            yml = cdir / showcase.CASE_YAML
            if not yml.is_file():
                err(f"{rel}: 缺 {showcase.CASE_YAML}")
                continue
            try:
                meta = showcase.parse_case(yml)
            except showcase.ShowcaseError as e:
                err(str(e))
                continue
            for problem in showcase.check_case(meta, cdir, known_modules=known):
                err(f"{rel}: {problem}")
    return n


def run_verify(target_env="container"):
    """跑 verify 块。哨兵 cron 用这个发现工具链变更。

    机验的语义是「这条切片教的命令在当前版本还存在吗」，
    不是「学员做没做作业」。跑不通 = 内容可能过时，开 Issue。

    **必须按 env 过滤**：`own-mac` 切片的机验依赖学员本机环境
    （回环网关、个人 key），在容器里跑必然失败 —— 那是假警报，
    会让哨兵 Issue 迅速失去可信度。
    """
    import subprocess
    total = ok = skipped = 0
    for f in sorted(SLICES.rglob("*.md")):
        rel = str(f.relative_to(SLICES))[:-3]
        meta = parse_slice(f)
        if not meta or not meta["verify"]:
            continue
        if meta.get("env") != target_env:
            skipped += len(meta["verify"])
            continue
        for v in meta["verify"]:
            total += 1
            try:
                r = subprocess.run(v["cmd"], shell=True, capture_output=True, timeout=60)
                passed = r.returncode == v["expect_exit"]
            except subprocess.TimeoutExpired:
                passed, r = False, None
            ok += passed
            mark = "  ok " if passed else "FAIL"
            print(f"  [{mark}] {rel:34} {v['cmd'][:46]}")
            if not passed and r is not None:
                tail = (r.stderr or r.stdout).decode("utf-8", "replace").strip().split("\n")
                if tail and tail[0]:
                    print(f"         -> exit={r.returncode} {tail[0][:70]}")
    print(f"\n  机验 {ok}/{total} 通过（env={target_env}）；"
          f"跳过 {skipped} 条其它环境的机验")
    return 1 if ok != total else 0


if __name__ == "__main__":
    if "--verify" in sys.argv:
        i = sys.argv.index("--verify")
        env = sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("-") \
            else "container"
        sys.exit(run_verify(env))
    sys.exit(main())
