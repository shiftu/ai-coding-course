"""精选案例库（showcase）：学员证据目录里的录屏 → 脱敏副本 → 仓库里所有学员可见。

这是**唯一**一条从证据到公开的路。三道闸，缺一不可：
  ① 只有管理员能跑 `sandctl showcase`（web 没有入口）；
  ② 副本经 redact 脱敏，原文件不动；
  ③ 落在 curriculum/showcase/ 里，走 git 提交 —— PR 就是审核。

老师不单独录"示范"：老师就是一个测评沙盒账号，录出来的东西和学员一样走这条路，
只在 case.yaml 里标 source: teacher。

存放形态（见设计文档 cast-replay-showcase.md §3.2）：
    curriculum/showcase/<module>/<verdict>-<slug>/
    ├── case.yaml       五个字段
    ├── session.cast    脱敏后的录屏
    └── notes.md        讲解，必填 —— 回放看得到「做了什么」，看不到「为什么」
"""
import os
import pathlib
import re
import sys

import redact
import store

_ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOWCASE_DIR = pathlib.Path(os.path.expanduser(
    os.environ.get("MICROCLASS_SHOWCASE", str(_ROOT / "curriculum" / "showcase"))))
TRACKS_DIR = _ROOT / "curriculum" / "tracks"
if str(_ROOT / "curriculum") not in sys.path:
    sys.path.insert(0, str(_ROOT / "curriculum"))
import validate as curriculum  # noqa: E402  轨道解析器（复用，不另写一份）

CASE_YAML = "case.yaml"
CAST_NAME = "session.cast"
NOTES_MD = "notes.md"
VERDICTS = ("good", "bad")
SOURCES = ("teacher", "student")
FIELDS = ("module", "verdict", "title", "source", "picked_by")
# 目录名会进 URL，收紧到和学员 ID 一样的字符集
SEG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")

NOTES_TEMPLATE = """\
> **入库前必须有人从头看一遍这段录屏。** 脱敏器只认已知模式（密钥前缀、学员 ID、
> 网关地址），一个密钥被终端拆成两段输出它就看不见。看完把这段引用删掉。

## 看什么

（这段录屏为什么值得看：好在哪 / 坏在哪。回放只显示做了什么，为什么要你来写。）

## 关键时刻

- 00:00 —
"""


class ShowcaseError(RuntimeError):
    pass


# ---- 读 ---------------------------------------------------------------------

def parse_case(path):
    """case.yaml 只认 `key: value`，和切片 frontmatter 一样的子集。超出即报错。"""
    meta = {}
    for n, raw in enumerate(pathlib.Path(path).read_text(encoding="utf-8").split("\n"), 1):
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        kv = re.match(r"^(\w+): (.+)$", line)
        if not kv:
            raise ShowcaseError(f"{path}:{n}: 无法解析 -> {raw!r}")
        meta[kv.group(1)] = kv.group(2).strip().strip('"')
    return meta


def check_case(meta, case_dir, known_modules=None):
    """一个案例的结构问题清单。空列表 = 合格。validate.py 和 add_case 共用。"""
    errs = []
    for k in FIELDS:
        if not meta.get(k):
            errs.append(f"缺字段 {k}")
    if meta.get("verdict") not in VERDICTS:
        errs.append(f"verdict {meta.get('verdict')!r} 不在 {VERDICTS}")
    if meta.get("source") not in SOURCES:
        errs.append(f"source {meta.get('source')!r} 不在 {SOURCES}")
    if known_modules is not None and meta.get("module") not in known_modules:
        errs.append(f"module {meta.get('module')!r} 不在任何轨道里")
    case_dir = pathlib.Path(case_dir)
    if case_dir.parent.name != meta.get("module"):
        errs.append(f"目录在 {case_dir.parent.name}/ 下，但 module 写的是 {meta.get('module')!r}")
    if meta.get("verdict") and not case_dir.name.startswith(meta["verdict"] + "-"):
        errs.append(f"目录名应以 {meta.get('verdict')}- 开头")
    cast = case_dir / CAST_NAME
    if not cast.is_file():
        errs.append(f"缺 {CAST_NAME}")
    else:
        head = _cast_header(cast)
        if head.get("version") != 2 or not head.get("width"):
            errs.append(f"{CAST_NAME} 不是可回放的 asciicast v2（version={head.get('version')!r}, "
                        f"width={head.get('width')!r}）")
    notes = case_dir / NOTES_MD
    if not notes.is_file() or not notes.read_text(encoding="utf-8").strip():
        errs.append(f"缺 {NOTES_MD} 或是空的 —— 讲解必填")
    elif "入库前必须有人从头看一遍" in notes.read_text(encoding="utf-8"):
        errs.append(f"{NOTES_MD} 还带着模板里的复核提示 —— 看完录屏再把它删掉")
    return errs


def _cast_header(path):
    import json
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return json.loads(f.readline())
    except (OSError, ValueError):
        return {}


def all_modules():
    """三条轨道里出现过的全部模块 id。"""
    out = {}
    for f in sorted(TRACKS_DIR.glob("track-*.yaml")):
        for mod in curriculum.parse_track(f)["modules"]:
            out.setdefault(mod["id"], mod)
    return out


def load_case(module, dirname):
    """读一个案例。路径段先过字符集，再确认真的在 SHOWCASE_DIR 里。不存在返回 None。"""
    if not (SEG_RE.match(module or "") and SEG_RE.match(dirname or "")):
        return None
    d = (SHOWCASE_DIR / module / dirname).resolve()
    if SHOWCASE_DIR.resolve() not in d.parents or not (d / CASE_YAML).is_file():
        return None
    try:
        meta = parse_case(d / CASE_YAML)
    except ShowcaseError:
        return None
    notes = d / NOTES_MD
    return {**meta, "dir": d, "module": module, "slug": dirname,
            "notes": notes.read_text(encoding="utf-8") if notes.is_file() else "",
            "has_cast": (d / CAST_NAME).is_file()}


def list_cases():
    """{module_id: [case, ...]}，每个模块内 good 在前、按目录名排。"""
    out = {}
    if not SHOWCASE_DIR.is_dir():
        return out
    for mdir in sorted(p for p in SHOWCASE_DIR.iterdir() if p.is_dir()):
        cases = [c for c in (load_case(mdir.name, d.name)
                             for d in sorted(p for p in mdir.iterdir() if p.is_dir())) if c]
        if cases:
            out[mdir.name] = sorted(cases, key=lambda c: (c.get("verdict") != "good", c["slug"]))
    return out


# ---- 写 ---------------------------------------------------------------------

def add_case(student, cast_name, *, module, verdict, title, slug, by, source="student", hosts=()):
    """学员证据目录里的一段录屏 → 脱敏副本 + case.yaml + notes.md 模板。

    **不 commit。** 留给人看完录屏、写完 notes 再提交 —— PR 就是审核。
    返回 (案例目录, 脱敏计数)。
    """
    if verdict not in VERDICTS:
        raise ShowcaseError(f"verdict 必须是 {VERDICTS}")
    if source not in SOURCES:
        raise ShowcaseError(f"source 必须是 {SOURCES}")
    if not SEG_RE.match(slug or ""):
        raise ShowcaseError("slug 只允许小写字母/数字/下划线/连字符，以字母数字开头")
    if module not in all_modules():
        raise ShowcaseError(f"模块 {module!r} 不在任何轨道里。看：curriculum/tracks/")
    if not title.strip():
        raise ShowcaseError("title 是空的")

    # 源文件：只在**这名学员自己的**证据目录里按文件名找，和 web 的白名单同一个规则
    if "/" in cast_name or "\\" in cast_name or not cast_name.endswith(".cast"):
        raise ShowcaseError(f"录屏文件名不合法：{cast_name!r}")
    src = pathlib.Path(store.evidence_dir(student)) / cast_name
    if not src.is_file():
        have = sorted(p.name for p in src.parent.glob("*.cast"))
        raise ShowcaseError(f"{student} 的证据目录里没有 {cast_name}。有的是：{have or '（空）'}")

    dst = SHOWCASE_DIR / module / f"{verdict}-{slug}"
    if dst.exists():
        raise ShowcaseError(f"{dst} 已存在 —— 换个 slug，或先删掉旧的")
    dst.mkdir(parents=True)
    try:
        counts = redact.redact_cast(src, dst / CAST_NAME, student=student, hosts=hosts)
    except ValueError as e:
        dst.rmdir() if not any(dst.iterdir()) else None
        raise ShowcaseError(str(e)) from None
    (dst / CASE_YAML).write_text(
        f"module: {module}\n"
        f"verdict: {verdict}\n"
        f"title: {title.strip()}\n"
        f"source: {source}\n"
        f"picked_by: {by}\n", encoding="utf-8")
    (dst / NOTES_MD).write_text(NOTES_TEMPLATE, encoding="utf-8")
    return dst, counts
