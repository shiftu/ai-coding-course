#!/usr/bin/env python3
"""五个页面的正文。路由在 serve.py，数据在 data.py，这里只管拼 HTML。"""
import json

import sitepath  # noqa: F401  先把 control/ 挂进 sys.path

import data
import render
import sandbox
from render import esc, md, page, radar_svg


# ---- 1. 登录 --------------------------------------------------------------

def login(*, dev_login=False, error="", open_id=""):
    if open_id:
        body = render.notice(
            f"你的飞书账号登录成功了，但平台上还没有对应的学员档案。\n\n"
            f"把下面这串 ID 发给管理员开通：\n\n```\n{open_id}\n```\n\n"
            f"开通命令：`sandctl create <你的学员ID>` 然后 "
            f"`sandctl bind <你的学员ID> --lark-open-id {open_id}`", "warn")
    elif error:
        body = render.notice(f"登录没成功：{error}", "err")
    else:
        body = "<p>用公司飞书账号登录。平台只读取你的 open_id，不读姓名、邮箱、部门。</p>"
    btns = ['<p><a class="btn" href="/auth/lark/start">用飞书登录</a></p>']
    if dev_login:
        btns.append(
            '<form class="devlogin" method="post" action="/auth/dev">'
            '<p><strong>开发模式</strong>：没有配飞书应用，直接填学员 ID 进去。'
            '这个入口只在监听回环时存在。</p>'
            '<input name="student" placeholder="学员 ID，如 stu-diligent" required>'
            '<button type="submit">进去</button></form>')
    return page("登录", body + "".join(btns))


# ---- 2. 测评 --------------------------------------------------------------

def assess(rec, *, base_path):
    student = rec["student"]
    state = sandbox.container_state(student)
    if data.graduated(rec):
        body = render.notice(
            "你已经毕业了。沙盒和采集都已经停止，测评终端不再提供。\n\n"
            "这是设计上的硬边界：**毕业即零采集**（设计文档 §8）。", "info")
        return page("测评", body, student=student, active="/assess")

    task_path = f"/workspace/{sandbox.task_dir(rec.get('track'))}"
    head = md(
        f"测评任务在容器里的 `{task_path}`。20 分钟，任务量故意略超时长——"
        "**收窄范围本身就是被判定的一项**。\n\n"
        "- 终端里的 `claude` / `codex` 已经接好内部网关，不用你填任何 key\n"
        "- 敲 `card` 看速查卡\n"
        "- 全程录屏 + 会话记录，用来出你的证据页。判定规则是公开的："
        "`curriculum/rubric/rubric.md`")

    if rec.get("ttyd_base_path") != base_path:
        # 老容器（或改过前缀之后没重建的）：ttyd 还挂在别的路径上，反代过去是 404。
        # 与其给学员一块白屏，不如直说。
        term = render.notice(
            f"你的容器建得比较早，里面的终端挂在 `{esc(rec.get('ttyd_base_path') or '/')}`，"
            f"而前端现在按 `{esc(base_path)}` 反代 —— 代过去只会 404。\n\n"
            f"请管理员重建：`sandctl destroy {esc(student)} --keep-volume` 然后 "
            f"`sandctl create {esc(student)}`。卷里的东西不会丢。", "err")
    elif state == "running":
        term = (f'<iframe class="term" src="{base_path}/" '
                f'title="沙盒终端" allow="clipboard-read; clipboard-write"></iframe>'
                f'<p class="hint">终端连的是你自己的容器，账号口令由平台代填，'
                f'不会经过浏览器。</p>')
    elif state == "absent":
        term = render.notice(
            "你的容器还没建起来。这一步必须管理员来做（`sandctl create`）——"
            "Web 登录不能创建容器，否则谁都能把宿主机的卷和端口耗光。", "err")
    else:
        term = ('<form method="post" action="/assess/start">'
                f'<p>你的沙盒当前是 <code>{esc(state)}</code>。</p>'
                '<button class="btn" type="submit">启动我的沙盒</button></form>')
    return page("测评", head + term, student=student, active="/assess")


# ---- 3. 我的轨道 ----------------------------------------------------------

def track(rec):
    student = rec["student"]
    tid = rec.get("track")
    if not tid:
        return page("我的轨道", render.notice(
            "还没给你分轨道。轨道由测评结果决定（快筛未过 → A，多维 L1–L2 → B，"
            "以此类推），管理员定档后这里就有内容了。", "warn"),
            student=student, active="/track")
    trk = data.track(tid)
    if not trk:
        return page("我的轨道", render.notice(
            f"档案里写的是轨道 {esc(tid)}，但 `curriculum/tracks/track-{esc(tid)}.yaml` "
            f"读不出来。这是内容仓库的问题，请管理员看一眼。", "err"),
            student=student, active="/track")

    pr = data.progress(rec, trk)
    rows = []
    for m in pr["rows"]:
        slices = "".join(
            f'<li><code>{esc(s["id"])}</code> '
            f'<span class="tag">{esc(s.get("type", "?"))}</span> '
            f'<span class="tag">{esc(s.get("env", "?"))}</span> '
            f'{esc(s.get("dimension", ""))} · {esc(s.get("level_edge", ""))}</li>'
            if s else '<li class="err">切片文件缺失</li>'
            for s in m["slice_metas"])
        exempt = (f'<p class="exempt"><strong>免修考</strong>：{esc(m["exempt_test"])}</p>'
                  if m.get("exempt_test") else
                  '<p class="exempt muted">这个模块没有免修考，必须走完。</p>')
        at = f'<span class="muted">（{esc(m["at"])}）</span>' if m.get("at") else ""
        rows.append(
            f'<details class="mod {"done" if m["state"] else ""}">'
            f'<summary><span class="state">{esc(m["state_text"])}</span>'
            f'<b>{esc(m.get("name", m["id"]))}</b> '
            f'<span class="tag">{esc(m.get("kind", ""))}</span>{at}</summary>'
            f'{exempt}<ul class="slices">{slices}</ul></details>')

    head = md(
        f"**轨道 {tid} · {trk.get('name', '')}** —— {trk.get('enter_when', '')}\n\n"
        f"进度 {pr['done']} / {pr['total']} 个模块。")
    note = render.notice(
        "进度只记录**已经通过的免修考或模块验收**，由人工/免修考写进档案。"
        "没有记录就是未开始 —— 这里不从你的容器活动、证据或任何别的地方"
        "推断进度。推断出来的进度会让人以为自己学过了。", "info")
    return page("我的轨道", head + note + "".join(rows),
                student=student, active="/track")


# ---- 4. 能力雷达 ----------------------------------------------------------

def me(rec):
    student = rec["student"]
    g = data.latest_graded(student)
    if not g:
        return page("能力雷达", render.notice(
            "还没有判过分的测评。做完测评、管理员跑过采证与批改之后，"
            "这里会出现你的四维雷达图和每一条判定的证据链接。", "info"),
            student=student, active="/me")

    grade = g["grade"]
    dims = grade.get("dimensions") or {}
    svg = radar_svg(dims)

    trs = []
    for d in render.DIMS:
        info = dims.get(d) or {}
        lv = info.get("level", "未测得")
        edges = "".join(
            f'<li><code>{esc(k)}</code> {esc(v.get("state"))}'
            + (f' · {", ".join(esc(i) for i in v.get("items") or [])}'
               if v.get("items") else " · 本次没有判定条目")
            + "</li>"
            for k, v in (info.get("edges") or {}).items())
        trs.append(
            f'<tr><td><b>{esc(d)}</b></td>'
            f'<td class="{"lv" if lv in render.LEVEL_ORDER else "lv missing"}">{esc(lv)}</td>'
            f'<td>{esc(info.get("reason") or "")}<ul class="edges">{edges}</ul></td></tr>')

    s1 = grade.get("s1")
    s1_text = {"pass": "通过", "fail": "未通过"}.get(s1, "未测得")
    s1_items = grade.get("s1_failed_items") or []
    s1_box = render.notice(
        f"**S1 安全闸：{s1_text}**"
        + (f"\n\n踩到的条目：" + "".join(f"\n- `{i}`" for i in s1_items) if s1_items else "")
        + "\n\nS1 是资格闸，不参与等级加分：未通过就不解锁 L2 内容，"
          "**能封顶，但不会把你的维度等级压低**。",
        "err" if s1 == "fail" else ("ok" if s1 == "pass" else "warn"))

    overall = grade.get("overall")
    unmeasured = grade.get("unmeasured_dimensions") or []
    ov = render.notice(
        f"**总等级：{overall}**"
        + (f"\n\n四维里还有没测到的（{'、'.join(unmeasured)}）。短板决定制要求四维齐全"
           f"才能取最小值 —— **有洞的向量不能取 min**，所以先记待补测，由后续作业补上。"
           if overall == "待补测" else ""),
        "warn" if overall == "待补测" else "ok")

    blank = ('<div class="notice err">' + md(
        "**本次没有任何修改或测试动作。** 所有质量类判定都带前置条件，一行没改就全判 n/a，"
        "于是四维显示未测得而不是低分。这在逻辑上是对的，但**未测得不等于通过** —— "
        "总等级记待补测，并会进人工抽查。") + "</div>") if grade.get("blank_submission") else ""

    debrief = ""
    if g["debrief"].is_file():
        debrief = ('<details class="debrief"><summary>完整复盘（含埋点揭晓）</summary>'
                   + md(g["debrief"].read_text(encoding="utf-8")) + "</details>")

    body = (f'<div class="radarwrap">{svg}{render.RADAR_LEGEND}</div>'
            + ov + s1_box + blank
            + '<table class="dims"><thead><tr><th>维度</th><th>等级</th>'
              '<th>依据</th></tr></thead><tbody>' + "".join(trs) + "</tbody></table>"
            + f'<p class="muted">判定时间 {esc(grade.get("graded_at"))} · '
              f'合并了 {esc(grade.get("session_count"))} 段会话 · '
              f'<a href="/evidence">看证据</a></p>'
            + debrief)
    return page("能力雷达", body, student=student, active="/me")


# ---- 5. 我的证据 ----------------------------------------------------------

def evidence(rec):
    student = rec["student"]
    banner = ""
    if data.graduated(rec):
        banner = render.notice(
            f"你已于 {esc(rec['graduated_at'])} 毕业，**采集已经停止**"
            f"（网关 key 已吊销、容器已停）。下面是毕业之前采到的东西，"
            f"它属于你，不会再增加。", "info")

    g = data.latest_graded(student)
    blocks = []

    man = (g or {}).get("manifest") or {}
    if man:
        src = man.get("sources") or {}
        rows = "".join(
            f'<tr><td><code>{esc(k)}</code></td><td>{esc(json.dumps(v, ensure_ascii=False)[:160])}</td></tr>'
            for k, v in src.items())
        empt = man.get("empty_sources") or []
        q = man.get("quiescent")
        blocks.append(
            "<h2>采证清单</h2>"
            + render.notice(
                f"采于 {esc(man.get('harvested_at'))}，静止态："
                + ("**是** —— 采的时候容器里没有 agent 在跑，证据是完整的一份快照。"
                   if q else
                   "**否** —— 采的时候还有 agent 在跑，这份证据可能只截到一半。")
                + (f"\n\n空的来源：{'、'.join(empt)}。空不等于没做，也不等于做了 —— "
                   f"只表示这一路没采到东西。" if empt else ""),
                "ok" if q else "warn")
            + f'<table class="src"><tbody>{rows}</tbody></table>')

    if g:
        ev = (g["grade"].get("evidence") or {})
        res = (g["grade"].get("results") or {})
        items = []
        for iid, verdict in res.items():
            v = verdict.get("verdict")
            why = verdict.get("why") or verdict.get("reason") or ""
            links = "".join(
                f'<li><span class="seq">#{e.get("seq")}</span> '
                f'<code>{esc(e.get("tool"))}</code> '
                f'<span class="uuid">{esc(e.get("uuid"))}</span>'
                f'<pre>{esc((e.get("excerpt") or "")[:400])}</pre></li>'
                for e in (ev.get(iid) or []))
            items.append(
                f'<details class="item v-{esc(v)}"><summary>'
                f'<span class="verdict">{esc(v)}</span><code>{esc(iid)}</code>'
                f'<span class="muted"> {esc(why)}</span></summary>'
                + (f'<ul class="ev">{links}</ul>' if links
                   else '<p class="muted">这一条没有引用到具体的工具调用。</p>')
                + "</details>")
        blocks.append("<h2>每一条判定的证据</h2>" + "".join(items))

    casts = data.cast_files(student)
    if casts:
        lis = "".join(
            f'<li><a href="/evidence/cast/{esc(c.name)}">{esc(c.name)}</a> '
            f'（{c.stat().st_size} 字节）—— 下载后 <code>asciinema play {esc(c.name)}</code></li>'
            for c in casts)
        blocks.append("<h2>录屏</h2><ul>" + lis + "</ul>")

    hs = data.harvests(student)
    if hs:
        lis = "".join(f"<li><code>{esc(h.name)}</code></li>" for h in hs)
        blocks.append(f'<h2>全部采证批次</h2><ul class="muted">{lis}</ul>')

    if not blocks:
        blocks = [render.notice("还没有采到任何证据。", "info")]
    return page("我的证据", banner + "".join(blocks), student=student, active="/evidence")
