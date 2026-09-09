#!/usr/bin/env python3
"""HTML 渲染。服务端出完整页面，没有构建步骤、没有前端框架。

100 人/年的内部平台，装一套打包链只会多一个会腐烂的东西。
唯一的 JS 是雷达图上的一句 title —— 连它都不是必需的。
"""
import html
import math
import re

# 四维在雷达图上的固定顺序（顺时针从正上方开始）。
DIMS = ("工具操作", "需求表达", "质量验证", "自动化编排")
LEVEL_ORDER = ("L0", "L1", "L2", "L3", "L4")
# 本次 rubric 只判到 L2，L3/L4 走作品制。雷达图必须把这件事画出来，
# 否则"最外两圈永远够不着"看起来像学员的问题。
RUBRIC_TOP = "L2"


def esc(s):
    return html.escape(str(s if s is not None else ""))


# ---- 极简 markdown ---------------------------------------------------------
# 只够渲染 debrief.md 和切片正文。**先整体转义再加标签**，
# 所以内容里的 <script> 只会变成字面文字。
_INLINE = ((re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
           (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"))


def _inline(text):
    out = esc(text)
    for pat, rep in _INLINE:
        out = pat.sub(rep, out)
    return out


def md(text):
    """markdown 子集 → HTML：标题、列表、表格、引用、围栏代码、段落。"""
    lines = (text or "").split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{esc(chr(10).join(buf))}</code></pre>")
            continue
        h = re.match(r"^(#{1,4})\s+(.*)$", line)
        if h:
            lv = len(h.group(1)) + 1        # 页面里已有 h1，正文从 h2 起
            out.append(f"<h{lv}>{_inline(h.group(2))}</h{lv}>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1]):
            head = [c.strip() for c in line.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                         for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            continue
        if line.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf))}</blockquote>")
            continue
        if line.strip():
            buf = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", ">", "```")) \
                    and not re.match(r"^\s*[-*]\s+", lines[i]):
                buf.append(lines[i])
                i += 1
            out.append(f"<p>{_inline(' '.join(buf))}</p>")
            continue
        i += 1
    return "\n".join(out)


# ---- 雷达图 ----------------------------------------------------------------

def _r(level, R):
    """等级 → 半径。L0 也占一点半径，否则它和"没有数据"在图上长得一样。"""
    return R * (0.16 + 0.21 * LEVEL_ORDER.index(level))


def radar_svg(dims, size=380):
    """四维雷达图。

    **未测得的维度不画顶点，多边形就在那里断开。** 这是整张图最要紧的一件事：
    把未测得画成 0 会让人以为自己在那一维得了最低分，而事实是那一维这次
    根本没测。断口 + 虚线轴 + 空心方块，看一眼就知道是"缺一块"而不是"很差"。
    """
    cx = cy = size / 2
    R = size * 0.34
    ang = [-math.pi / 2 + i * math.pi / 2 for i in range(4)]   # 上 右 下 左

    def xy(i, r):
        return cx + r * math.cos(ang[i]), cy + r * math.sin(ang[i])

    parts = []
    # 参考环。L3/L4 两圈单独一种样式：本次测评压根不覆盖它们。
    for lv in LEVEL_ORDER:
        r = _r(lv, R)
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, r) for i in range(4)))
        beyond = LEVEL_ORDER.index(lv) > LEVEL_ORDER.index(RUBRIC_TOP)
        cls = "ring beyond" if beyond else "ring"
        parts.append(f'<polygon class="{cls}" points="{pts}" />')
        lx, ly = xy(0, r)
        parts.append(f'<text class="ringlabel{" beyond" if beyond else ""}" '
                     f'x="{lx + 6:.1f}" y="{ly + 4:.1f}">{lv}</text>')

    measured = []
    for i, d in enumerate(DIMS):
        info = dims.get(d) or {}
        lv = info.get("level")
        ok = lv in LEVEL_ORDER
        ex, ey = xy(i, R * 1.06)
        parts.append(f'<line class="axis{"" if ok else " missing"}" x1="{cx}" y1="{cy}" '
                     f'x2="{ex:.1f}" y2="{ey:.1f}" />')
        if ok:
            px, py = xy(i, _r(lv, R))
            measured.append((i, px, py))
            parts.append(f'<circle class="vtx" cx="{px:.1f}" cy="{py:.1f}" r="5">'
                         f'<title>{esc(d)} {esc(lv)}</title></circle>')
        else:
            mx, my = xy(i, R)
            parts.append(f'<rect class="gap" x="{mx - 5:.1f}" y="{my - 5:.1f}" width="10" height="10">'
                         f'<title>{esc(d)}：未测得</title></rect>')
        # 维度标签
        tx, ty = xy(i, R * 1.30)
        anchor = "middle" if i in (0, 2) else ("start" if i == 1 else "end")
        parts.append(f'<text class="dimlabel" x="{tx:.1f}" y="{ty + 4:.1f}" '
                     f'text-anchor="{anchor}">{esc(d)}</text>')
        parts.append(f'<text class="dimlevel{"" if ok else " missing"}" x="{tx:.1f}" '
                     f'y="{ty + 20:.1f}" text-anchor="{anchor}">{esc(lv or "未测得")}</text>')

    # 只连"相邻两维都测到了"的边。谁旁边是洞，谁那条边就不画。
    for a in range(4):
        b = (a + 1) % 4
        pa = next((p for p in measured if p[0] == a), None)
        pb = next((p for p in measured if p[0] == b), None)
        if pa and pb:
            parts.append(f'<line class="edge" x1="{pa[1]:.1f}" y1="{pa[2]:.1f}" '
                         f'x2="{pb[1]:.1f}" y2="{pb[2]:.1f}" />')

    return (f'<svg class="radar" viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'role="img" aria-label="四维能力雷达图">' + "".join(parts) + "</svg>")


RADAR_LEGEND = """
<ul class="legend">
  <li><span class="k vtx"></span>测到的等级</li>
  <li><span class="k gap"></span>未测得 —— 这一维本次<strong>没有可判定的场景</strong>，
      不是低分。图上是个断口，不是零。</li>
  <li><span class="k beyond"></span>L3 / L4 走作品制，本次测评不覆盖。</li>
</ul>"""


# ---- 页面骨架 --------------------------------------------------------------

NAV = (("/assess", "测评"), ("/track", "我的轨道"),
       ("/me", "能力雷达"), ("/evidence", "我的证据"))


def page(title, body, *, student=None, active="", banner=""):
    nav = "".join(
        f'<a href="{p}" class="{"on" if p == active else ""}">{esc(t)}</a>'
        for p, t in NAV) if student else ""
    who = (f'<span class="who">{esc(student)}'
           f'<a class="out" href="/logout">退出</a></span>') if student else ""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · AI 微课堂</title>
<link rel="stylesheet" href="/static/style.css"></head>
<body>
<header><a class="brand" href="/track">AI 微课堂</a><nav>{nav}</nav>{who}</header>
{banner}
<main><h1>{esc(title)}</h1>
{body}
</main>
<footer>判定规则全文见 <code>curriculum/rubric/rubric.md</code>。
不认同任何一条判定都可以申诉。</footer>
</body></html>"""


def notice(text, kind="info"):
    return f'<div class="notice {kind}">{md(text)}</div>'
