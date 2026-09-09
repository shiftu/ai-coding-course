#!/usr/bin/env python3
"""只读数据层：把已经落盘的东西读成页面要的形状。

**前端不产生任何新事实。** 学员档案由 sandctl 写，证据由 harvest 写，
判定由 grade 写，课程内容在 curriculum/ 里。这一层只做三件事：
找到最新的那份、解析、原样交给渲染层。

读不到就返回 None，让页面显示「没有」——绝不用默认值或推断把洞填上。
这是整套系统的一贯立场（见 rubric.md：未测得 ≠ 通过 ≠ 不及格）。
"""
import json
import pathlib

from sitepath import ROOT

import store                      # noqa: E402  学员档案
import validate as curriculum     # noqa: E402  切片/轨道解析器（复用，不另写一份）

SLICES_DIR = ROOT / "curriculum" / "slices"
TRACKS_DIR = ROOT / "curriculum" / "tracks"
RUBRIC_MD = ROOT / "curriculum" / "rubric" / "rubric.md"

# 模块进度只认这几种状态。没有记录 = 未开始，不做任何推断。
MODULE_STATES = ("exempt", "pass")
STATE_TEXT = {"exempt": "免修通过", "pass": "已完成", None: "未开始"}


# ---- 学员 -----------------------------------------------------------------

def student_by_lark(open_id):
    """飞书 open_id → 学员档案。找不到返回 None。

    故意不做自助开通：Web 登录不能创建容器，否则任何一个能走完 SSO 的人
    都能把宿主机的卷和端口耗光。开通走 `sandctl create` + `sandctl bind`。
    """
    if not open_id:
        return None
    for rec in store.all_students():
        if rec.get("lark_open_id") == open_id:
            return rec
    return None


def graduated(rec):
    return bool(rec.get("graduated_at"))


# ---- 证据与批改 ------------------------------------------------------------

def harvests(student):
    """按时间倒序列出这名学员的全部采证批次。"""
    d = pathlib.Path(store.evidence_dir(student))
    if not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if p.is_dir() and p.name.startswith("harvest-")),
                  key=lambda p: p.name, reverse=True)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def latest_graded(student):
    """最近一批**判过分的**采证。

    注意不是「最近一批采证」：harvest 可以跑很多次，只有跑过 grade 的那几批
    才有 grade.json。挑最新的已判定批次，而不是最新的目录 —— 否则一次
    刚做完的采证会让雷达图凭空消失。
    """
    for h in harvests(student):
        g = _read_json(h / "grade" / "grade.json")
        if g:
            return {"dir": h, "grade": g, "manifest": _read_json(h / "manifest.json"),
                    "debrief": (h / "grade" / "debrief.md")}
    return None


def cast_files(student):
    d = pathlib.Path(store.evidence_dir(student))
    return sorted(d.glob("*.cast")) if d.is_dir() else []


# ---- 课程内容 --------------------------------------------------------------

_slice_cache = {}


def slice_meta(slice_id):
    """切片的 frontmatter + 正文。解析器复用 curriculum/validate.py。"""
    if slice_id in _slice_cache:
        return _slice_cache[slice_id]
    path = SLICES_DIR / f"{slice_id}.md"
    if not path.is_file():
        _slice_cache[slice_id] = None
        return None
    meta = curriculum.parse_slice(path) or {}
    text = path.read_text(encoding="utf-8")
    body = text.split("---\n", 2)[-1].strip()
    out = {**meta, "id": slice_id, "body": body}
    _slice_cache[slice_id] = out
    return out


def track(track_id):
    path = TRACKS_DIR / f"track-{track_id}.yaml"
    if not path.is_file():
        return None
    t = curriculum.parse_track(path)
    for mod in t["modules"]:
        mod["slice_metas"] = [slice_meta(s) for s in mod["slices"]]
    return t


def progress(rec, trk):
    """把档案里记录的模块状态套到轨道上。

    只读 rec['modules']，那是人工/免修考写进去的。**没有记录就是未开始**——
    不从证据、不从容器活动、不从任何别的地方推断进度。推断出来的进度
    会让人以为自己学过了。
    """
    recorded = rec.get("modules") or {}
    rows, done = [], 0
    for mod in (trk or {}).get("modules", []):
        st = (recorded.get(mod["id"]) or {})
        state = st.get("state") if st.get("state") in MODULE_STATES else None
        done += 1 if state else 0
        rows.append({**mod, "state": state, "state_text": STATE_TEXT[state],
                     "at": st.get("at"), "by": st.get("by")})
    return {"rows": rows, "done": done, "total": len(rows)}
