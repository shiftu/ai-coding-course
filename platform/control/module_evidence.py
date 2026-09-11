"""模块验收的线索检索：把学员证据里和某个模块沾边的片段捞出来给人看。

「我的轨道」的进度只认 `sandctl module` 手写的记录（见 sandctl.cmd_module），
判的依据是轨道文件里那行 `exempt_test`。设计文档 §5.2 说交付物由批改 agent 打分，
但批改 agent 目前只对测评实现了（rubric/grade.py）—— 模块验收是纯人工，
管理员得自己翻 harvest 目录里的 jsonl、回放 .cast。这个模块把「翻」这一步收掉。

**它不判定。** 输出的是线索：哪个时刻、哪份记录里出现过和这个模块相关的动作。
免修与否仍然按 exempt_test 人工验收，然后 `sandctl module … --state exempt`。
自动把线索当结论，就是页面上那句「推断出来的进度会让人以为自己学过了」。

三路来源，各有盲区，盲区必须印出来而不是默默留空：
  ① claude-code 会话   卷里 .claude/projects/**/*.jsonl —— 只有 claude-code
  ② codex 会话         卷里 .codex/sessions/**/*.jsonl  —— 只有 codex
  ③ 录屏               /evidence/*.cast —— 覆盖终端里的一切（含 hermes），
                       但 §4.3 只在测评模式录；course 模式的学员这一路天然是空的
hermes 自己的状态是 sqlite，不读；它的操作只能靠 ③。
"""
import datetime
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unicodedata

import harvest
import store

_ROOT = pathlib.Path(__file__).resolve().parents[2]
TRACKS_DIR = _ROOT / "curriculum" / "tracks"
if str(_ROOT / "curriculum") not in sys.path:
    sys.path.insert(0, str(_ROOT / "curriculum"))
import validate as curriculum  # noqa: E402  轨道解析器（复用，不另写一份）


class ModuleEvidenceError(RuntimeError):
    pass


# 模块 id → 在证据里找什么。模块 id 跨轨道共用（m0-env 在 A/B/C 里是同一个模块，
# exempt_test 也一字不差），所以表按模块 id 建，不按轨道。
# 关键词是从 exempt_test 和切片 id 里抽的：能在命令行 / 对话里留下痕迹的那些词。
# 大小写不敏感。
PATTERNS = {
    "m0-env":     (r"--version", r"/v1/models", r"microclass-(doctor|selfcheck)",
                   r"ANTHROPIC_BASE_URL", r"\b7421\b"),
    "m1-map":     (r"milestone", r"gitea", r"\btea\b", r"issue"),
    "m2-pair":    (r"\bclaude\b", r"\bcodex\b", r"git (checkout|switch) -b", r"\bdiff\b",
                   r"pull request|\bPR\b|收窄|计划"),
    "m3-hermes":  (r"hermes", r"profile", r"memor(y|ies)|记住|偏好",
                   r"checkpoint|rollback|回滚", r"\bskill"),
    "m4-spec":    (r"\bspec\b", r"验收标准|acceptance", r"不做什么|out of scope|范围"),
    "m5-quality": (r"pytest", r"\bassert\b", r"tests?/test_", r"失败断言|全绿|red.?green|TDD"),
    "m6-data":    (r"\bDAU\b", r"口径", r"\bSELECT\b", r"\bsql\b", r"metric"),
    "m7-auto":    (r"\bcron", r"schedule", r"webhook", r"定时"),
    "m8-lark":    (r"lark", r"飞书", r"bitable"),
    "m9-redline": (r"usage|用量", r"secret|密钥", r"gitleaks|trufflehog", r"rotat|轮换",
                   r"approval|审批", r"budget|预算"),
}

# 明确登记为「不在会话/录屏里」的模块，免得被误当成漏登记。
NO_PATTERNS = {
    "capstone": "毕业项目的交付物是 PR，在 Gitea 上看，不在会话/录屏里",
}


# ---- 轨道与模块 --------------------------------------------------------------

def module_of(rec, module_id):
    """学员所在轨道里的这个模块。不在这条轨道上就报错 —— 标了也不会显示。"""
    tid = rec.get("track")
    if not tid:
        raise ModuleEvidenceError(f"{rec['student']} 还没分轨道，没有模块可验")
    trk = track_modules(tid)
    for m in trk:
        if m["id"] == module_id:
            return m
    raise ModuleEvidenceError(
        f"轨道 {tid} 里没有模块 {module_id}。这条轨道上的模块："
        + "、".join(m["id"] for m in trk))


def track_modules(tid):
    path = TRACKS_DIR / f"track-{tid}.yaml"
    if not path.is_file():
        raise ModuleEvidenceError(f"读不到 {path}")
    return curriculum.parse_track(path)["modules"]


# ---- 三路来源，各自摊成同一种形状：{"when", "kind", "text", "where"} -------------

def _short_iso(ts):
    # "2026-08-25T11:29:41.229Z" → "08-25 11:29"
    return ts[5:16].replace("T", " ") if isinstance(ts, str) and len(ts) >= 16 else "?"


def _claude_where(path):
    # .claude/projects/-workspace-task-b/04056b45-….jsonl → "task-b/04056b45"
    proj = path.parent.name.replace("-workspace", "").lstrip("-") or "~"
    return f"{proj}/{path.stem[:8]}"


def _codex_where(path):
    # rollout-2026-09-09T10-04-23-<uuid>.jsonl → "codex 09-09T10-04"
    m = re.search(r"\d{4}-(\d{2}-\d{2}T\d{2}-\d{2})", path.name)
    return f"codex {m.group(1)}" if m else path.stem[:16]


def _tool_text(name, inp):
    if name == "Bash" and isinstance(inp, dict) and isinstance(inp.get("command"), str):
        return inp["command"]
    return json.dumps(inp, ensure_ascii=False)


def claude_items(root):
    """claude-code 会话里学员说的话 + 每次工具调用。tool_result 不要 —— 那是环境说的。"""
    items = []
    for path in sorted(pathlib.Path(root).rglob("*.jsonl")):
        where = _claude_where(path)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") not in ("user", "assistant"):
                continue
            when = _short_iso(rec.get("timestamp"))
            content = (rec.get("message") or {}).get("content")
            if isinstance(content, str):
                items.append({"when": when, "kind": "说", "text": content, "where": where})
                continue
            for block in content or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    items.append({"when": when, "kind": block.get("name", "?"),
                                  "text": _tool_text(block.get("name"), block.get("input")),
                                  "where": where})
    return items


def codex_items(root):
    """codex rollout 里学员的 user message + function_call。
    developer 消息和 <environment_context> 之类的注入不算学员说的。"""
    items = []
    for path in sorted(pathlib.Path(root).rglob("*.jsonl")):
        where = _codex_where(path)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "response_item":
                continue
            p = rec.get("payload") or {}
            when = _short_iso(rec.get("timestamp"))
            if p.get("type") == "message" and p.get("role") == "user":
                for c in p.get("content") or []:
                    t = c.get("text") if isinstance(c, dict) else None
                    if isinstance(t, str) and not t.lstrip().startswith("<"):
                        items.append({"when": when, "kind": "说", "text": t, "where": where})
            elif p.get("type") == "function_call":
                items.append({"when": when, "kind": p.get("name", "call"),
                              "text": str(p.get("arguments", "")), "where": where})
    return items


# 终端转义：CSI、OSC、其它 ESC 序列。去掉之后剩下的才是人眼看到的字。
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


def _clean(s):
    """去转义、按退格回删 —— readline 回显 `\\b \\b` 来擦字，不处理就会留下打错的半截。"""
    out = []
    for ch in _ANSI.sub("", s):
        if ch in "\x08\x7f":
            if out:
                out.pop()
        elif ch >= " " or ch == "\t":
            out.append(ch)
    return "".join(out).strip()


def cast_lines(path):
    """asciinema v2 → (头, [(偏移秒, 行)])。

    录屏只有输出事件（没开 --stdin），学员敲的命令是以回显的形式出现的。
    TUI 程序会把同一行重画几百次，这里不去重 —— 去重是 cast_items 的事，
    因为「重画了多少次」本身要印出来。
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        try:
            header = json.loads(f.readline())
        except json.JSONDecodeError:
            header = {}
        buf, out = "", []
        for line in f:
            try:
                t, kind, data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if kind != "o" or not isinstance(data, str):
                continue
            buf += data
            parts = re.split(r"\r\n|\n|\r", buf)
            buf = parts.pop()
            out += [(t, c) for c in map(_clean, parts) if c]
        if _clean(buf):
            out.append((t, _clean(buf)))
    return header, out


def _hms(sec):
    h, r = divmod(int(sec), 3600)
    return f"{h:02d}:{int(r // 60):02d}:{int(r % 60):02d}"


# 提示符后面跟的是学员敲的：bash 的 `root@xxx:~#`、claude/codex TUI 的 `>` / `❯`、hermes 的 `hermes>`。
# 提示符之前的输出是登录横幅（MOTD 里就有 claude / codex / hermes / lark-cli 四个词），不是学员。
_PROMPT = re.compile(r"^(?:\S+@\S+:[^\s#$]*[#$]|hermes>|codex>|[>❯])\s+(.*\S)")


def cast_items(evidence_dir):
    """每段录屏里每一行**第一次**出现的时刻，附重画次数。

    敲的和打印的分开：kind="敲" 是提示符后面学员输入的那行（提示符已剥掉），
    kind="" 是程序输出。验收看的是人做了什么，所以「敲」排前面；输出只是旁证 ——
    lark-cli --help 里也有 profile 和 skills 两个词，不能当成学员碰过 hermes。
    """
    items = []
    for name in sorted(f for f in os.listdir(evidence_dir) if f.endswith(".cast")):
        header, lines = cast_lines(os.path.join(evidence_dir, name))
        day = header.get("timestamp")
        day = (datetime.datetime.fromtimestamp(day, datetime.timezone.utc).strftime("%m-%d")
               if isinstance(day, (int, float)) else "?")
        first_prompt = next((i for i, (_, text) in enumerate(lines) if _PROMPT.match(text)), 0)
        first = {}
        for t, text in lines[first_prompt:]:
            m = _PROMPT.match(text)
            key = ("敲", m.group(1)) if m else ("", text)
            if key in first:
                first[key]["count"] += 1
            else:
                first[key] = {"when": f"{day} {_hms(t)}", "kind": key[0], "text": key[1],
                              "where": name, "count": 1}
        items += first.values()
    return items


# ---- 取证与匹配 --------------------------------------------------------------

def gather(student):
    """三路来源各自的条目。返回 {来源名: {"items", "files", "skipped"}}。

    读卷（① ②）是采集，毕业后按 §8 不再做；录屏是课程期内已落盘的既有证据，
    照旧可看。
    """
    rec = store.load(student)
    ev = store.evidence_dir(student)
    out = {}
    tmp = tempfile.mkdtemp(prefix="mc-evidence-")
    try:
        for key, sub, parse in (("claude", ".claude/projects", claude_items),
                                ("codex", ".codex/sessions", codex_items)):
            if not rec.get("collecting"):
                out[key] = {"items": [], "files": 0,
                            "skipped": f"已于 {rec.get('graduated_at')} 毕业，§8 之后不再读卷"}
                continue
            dest = os.path.join(tmp, key)
            n = harvest._copy_out(student, sub, dest)
            out[key] = {"items": parse(dest) if n else [], "files": n, "skipped": None}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    casts = [f for f in os.listdir(ev) if f.endswith(".cast")] if os.path.isdir(ev) else []
    skipped = None
    if not casts and rec.get("mode") != "assessment" and not rec.get("record"):
        skipped = (f"{rec.get('mode')} 模式登录不录屏（§4.3 只测评录；课程期要录得 "
                   f"sandctl create --record）—— hermes / codex 里的操作没有任何记录可查")
    out["cast"] = {"items": cast_items(ev) if casts else [], "files": len(casts), "skipped": skipped}
    return out


def match(items, patterns):
    pats = [re.compile(p, re.I) for p in patterns]
    return [it for it in items if any(p.search(it["text"]) for p in pats)]


# ---- 渲染 --------------------------------------------------------------------

SOURCE_LABEL = {"claude": ("①", "claude-code 会话", "份"),
                "codex":  ("②", "codex 会话", "份"),
                "cast":   ("③", "录屏", "段")}


def _one_line(s, width=96):
    s = " ".join(s.split())
    return s if len(s) <= width else s[:width - 1] + "…"


def _pad(s, n):
    """按终端显示宽度补齐 —— 中文占两格，f-string 的 :<n 只数码点，对不齐。"""
    w = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)
    return s + " " * max(0, n - w)


def _hit_lines(hits, limit):
    out = []
    for h in hits[:limit]:
        tag = f"  ×{h['count']}" if h.get("count", 1) > 1 else ""
        out.append(f"  {h['when']}  {_pad(h['where'], 18)}  {_pad(h['kind'], 7)}"
                   f"{_one_line(h['text'])}{tag}")
    if len(hits) > limit:
        out.append(f"  …还有 {len(hits) - limit} 处（--limit 看更多）")
    return out


def render_module(student, mod, sources, limit=20):
    lines = [f"{student} · {mod['id']}  {mod.get('name', '')}",
             f"  免修考  {mod.get('exempt_test') or '（这个模块没有免修考，必须走完）'}"]
    if mod["id"] in NO_PATTERNS:
        lines += [f"  线索    无 —— {NO_PATTERNS[mod['id']]}", ""]
        return "\n".join(lines)
    pats = PATTERNS.get(mod["id"])
    if not pats:
        lines += [f"  线索    这个模块还没登记搜索关键词（module_evidence.PATTERNS），只能人工翻", ""]
        return "\n".join(lines)
    lines += [f"  关键词  {' · '.join(pats)}", ""]

    for key, (mark, label, unit) in SOURCE_LABEL.items():
        src = sources[key]
        if src["skipped"]:
            lines += [f"{mark} {label}  未读 —— {src['skipped']}", ""]
            continue
        hits = match(src["items"], pats)
        head = f"{mark} {label}  {src['files']} {unit} · "
        if not hits:
            lines += [head + "无命中", ""]
            continue
        if key != "cast":
            lines += [head + f"命中 {len(hits)} 处", *_hit_lines(hits, limit), ""]
            continue
        typed = [h for h in hits if h["kind"] == "敲"]
        printed = [h for h in hits if h["kind"] != "敲"]
        lines.append(head + f"学员敲过 {len(typed)} 条 · 程序输出 {len(printed)} 行（重画已合并）")
        lines += _hit_lines(typed, limit)
        if printed:
            lines.append("  ── 输出里的，只是旁证 ──")
            lines += _hit_lines(printed, max(limit // 2, 3))
        lines.append("")

    lines += ["以上是线索，不是判定。免修与否按上面那行免修考人工验收，验过再记：",
              f"  sandctl module {student} {mod['id']} --state exempt --by <你>"]
    return "\n".join(lines)


def render_overview(student, modules, sources):
    """整条轨道每个模块三路命中数 —— 先看哪些模块值得细看。"""
    lines = [f"{student} 的轨道模块 · 线索命中数（不是进度，进度看 sandctl info）", ""]
    cols = (("①会话", 8), ("②codex", 8), ("③敲过", 8), ("③输出", 8))
    lines.append(_pad("模块", 12) + "".join(_pad(c, w) for c, w in cols) + "免修考")

    def counts(pats):
        if not pats:
            return ["—"] * 4
        cells = []
        for key in ("claude", "codex"):
            cells.append("未读" if sources[key]["skipped"] else str(len(match(sources[key]["items"], pats))))
        if sources["cast"]["skipped"]:
            cells += ["未读", "未读"]
        else:
            hits = match(sources["cast"]["items"], pats)
            cells += [str(sum(h["kind"] == "敲" for h in hits)), str(sum(h["kind"] != "敲" for h in hits))]
        return cells

    for m in modules:
        row = counts(None if m["id"] in NO_PATTERNS else PATTERNS.get(m["id"]))
        lines.append(_pad(m["id"], 12) + "".join(_pad(c, w) for c, (_, w) in zip(row, cols))
                     + _one_line(m.get("exempt_test") or "—", 60))
    lines += ["", "③敲过 = 提示符后面学员输入的行；③输出 = 程序打印的（--help、日志之类也会命中，只是旁证）"]
    for key, (mark, label, _) in SOURCE_LABEL.items():
        if sources[key]["skipped"]:
            lines.append(f"{mark} {label} 未读 —— {sources[key]['skipped']}")
    lines.append(f"细看某个模块：sandctl module-evidence {student} <模块id>")
    return "\n".join(lines)
