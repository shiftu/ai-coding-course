#!/usr/bin/env python3
"""module_evidence 的离线测试：三种记录格式的解析、去重、关键词表的完整性。

不碰 docker —— 解析器吃的是文件，这里就喂文件。
跑法：python3 test_module_evidence.py
"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import module_evidence as me  # noqa: E402

TMP = tempfile.mkdtemp(prefix="mc-evidence-test-")


def _jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_claude_items_take_student_words_and_tool_uses_only():
    root = os.path.join(TMP, "claude")
    _jsonl(os.path.join(root, "p", "s.jsonl"), [
        {"type": "user", "timestamp": "2026-08-25T11:29:41.229Z",
         "message": {"content": "帮我建个 cron"}},
        {"type": "assistant", "timestamp": "2026-08-25T11:29:47.979Z",
         "message": {"content": [{"type": "text", "text": "好"},
                                 {"type": "tool_use", "name": "Bash",
                                  "input": {"command": "crontab -l", "description": "list"}}]}},
        {"type": "user", "timestamp": "2026-08-25T11:29:48.000Z",
         "message": {"content": [{"type": "tool_result", "content": "cron 里有东西"}]}},
        {"type": "file-history-snapshot"},
    ])
    items = me.claude_items(root)
    assert [(i["kind"], i["text"]) for i in items] == [("说", "帮我建个 cron"), ("Bash", "crontab -l")]
    assert items[0]["when"] == "08-25 11:29"
    assert items[0]["where"] == "p/s"
    # tool_result 里的 "cron" 不能算学员的行为
    assert not any("有东西" in i["text"] for i in items)


def test_codex_items_skip_injected_context_and_developer_role():
    root = os.path.join(TMP, "codex")
    _jsonl(os.path.join(root, "2026", "rollout-2026-09-09T10-04-23-01a085a0.jsonl"), [
        {"type": "response_item", "timestamp": "2026-09-09T08:04:24.832Z",
         "payload": {"type": "message", "role": "developer",
                     "content": [{"type": "input_text", "text": "hermes skills instructions"}]}},
        {"type": "response_item", "timestamp": "2026-09-09T08:04:24.832Z",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "<environment_context> hermes </environment_context>"},
                                 {"type": "input_text", "text": "用 lark-cli 建文档"}]}},
        {"type": "response_item", "timestamp": "2026-09-09T08:04:30.000Z",
         "payload": {"type": "function_call", "name": "shell",
                     "arguments": "{\"command\":[\"lark-cli\",\"doc\",\"create\"]}"}},
        {"type": "event_msg", "payload": {"type": "token_count"}},
    ])
    items = me.codex_items(root)
    assert [(i["kind"], i["text"]) for i in items] == [
        ("说", "用 lark-cli 建文档"),
        ("shell", "{\"command\":[\"lark-cli\",\"doc\",\"create\"]}")]
    assert items[0]["where"] == "codex 09-09T10-04"


def test_cast_lines_strip_ansi_and_split_on_crlf():
    path = os.path.join(TMP, "a.cast")
    with open(path, "w") as f:
        f.write(json.dumps({"version": 2, "width": 80, "height": 24, "timestamp": 1787649039}) + "\n")
        f.write(json.dumps([0.5, "o", "[?2004hroot@x:~# hermes pro"]) + "\n")
        f.write(json.dumps([1.2, "o", "file list\r\n[32mok[0m\r\n"]) + "\n")
        f.write(json.dumps([2.0, "o", "tail"]) + "\n")
    header, lines = me.cast_lines(path)
    assert header["timestamp"] == 1787649039
    assert lines == [(1.2, "root@x:~# hermes profile list"), (1.2, "ok"), (2.0, "tail")]


def test_cast_lines_apply_backspaces():
    path = os.path.join(TMP, "bs.cast")
    with open(path, "w") as f:
        f.write(json.dumps({"version": 2}) + "\n")
        # 敲了 "curl"，退格四次擦掉，再敲 "cat x" —— readline 的回显就是这样
        f.write(json.dumps([1.0, "o", "root@x:~# curl\b \b\b \b\b \b\b \bcat x\r\n"]) + "\n")
    _, lines = me.cast_lines(path)
    assert lines == [(1.0, "root@x:~# cat x")]


def test_cast_items_split_typed_from_printed_and_drop_login_banner():
    ev = os.path.join(TMP, "ev")
    os.makedirs(ev, exist_ok=True)
    with open(os.path.join(ev, "session-1.cast"), "w") as f:
        f.write(json.dumps({"version": 2, "timestamp": 1787649039}) + "\n")
        # 登录横幅：提示符出现之前的输出，里面就有 hermes 这个词
        f.write(json.dumps([0.01, "o", "四件工具都装好了：claude / codex / hermes\r\n"]) + "\n")
        f.write(json.dumps([2.0, "o", "root@abc:~# claude\r\n"]) + "\n")
        for t in (3.0, 3.1, 3.2):                       # TUI 重画同一行三次
            f.write(json.dumps([t, "o", "> pytest -q\r\n"]) + "\n")
        f.write(json.dumps([70.0, "o", "1 failed\r\n"]) + "\n")
        f.write(json.dumps([80.0, "o", "root@abc:~# hermes profile list\r\n"]) + "\n")
    items = me.cast_items(ev)
    by = {(i["kind"], i["text"]): i for i in items}
    assert not any("四件工具" in t for _, t in by), "横幅不能算学员的"
    assert by[("敲", "claude")]["when"] == "08-25 00:00:02"          # 1787649039 是 2026-08-25 UTC
    assert by[("敲", "pytest -q")]["count"] == 3
    assert by[("敲", "pytest -q")]["when"] == "08-25 00:00:03"
    assert by[("", "1 failed")]["when"].endswith("00:01:10")
    assert by[("敲", "hermes profile list")]["where"] == "session-1.cast"


def test_cast_items_keep_everything_when_no_prompt_ever_appears():
    ev = os.path.join(TMP, "ev-noprompt")
    os.makedirs(ev, exist_ok=True)
    with open(os.path.join(ev, "s.cast"), "w") as f:
        f.write(json.dumps({"version": 2, "timestamp": 1787649039}) + "\n")
        f.write(json.dumps([1.0, "o", "only output here\r\n"]) + "\n")
    assert [i["text"] for i in me.cast_items(ev)] == ["only output here"]


def test_match_is_case_insensitive_regex():
    items = [{"text": "Hermes profile create"}, {"text": "ls -la"}, {"text": "我让它记住偏好"}]
    got = me.match(items, me.PATTERNS["m3-hermes"])
    assert [i["text"] for i in got] == ["Hermes profile create", "我让它记住偏好"]
    assert me.match(items, me.PATTERNS["m8-lark"]) == []


def test_every_module_in_every_track_is_registered():
    """新加模块忘了登记关键词，会在这里被抓住，而不是在验收时静默无命中。"""
    for tid in ("A", "B", "C"):
        for m in me.track_modules(tid):
            assert m["id"] in me.PATTERNS or m["id"] in me.NO_PATTERNS, (tid, m["id"])
    assert not set(me.PATTERNS) & set(me.NO_PATTERNS)


def test_module_of_rejects_module_outside_the_track():
    rec = {"student": "s", "track": "B"}
    assert me.module_of(rec, "m3-hermes")["exempt_test"]
    try:
        me.module_of(rec, "m2-pair")          # m2 只在 A 轨
    except me.ModuleEvidenceError as e:
        assert "轨道 B 里没有模块 m2-pair" in str(e)
    else:
        raise AssertionError("B 轨不该有 m2-pair")
    try:
        me.module_of({"student": "s", "track": None}, "m0-env")
    except me.ModuleEvidenceError as e:
        assert "还没分轨道" in str(e)
    else:
        raise AssertionError("没轨道也该报错")


def test_render_module_prints_blind_spots_instead_of_blank():
    mod = me.module_of({"student": "s", "track": "B"}, "m3-hermes")
    sources = {
        "claude": {"items": [{"when": "08-25 11:33", "kind": "Bash", "text": "hermes profile create",
                              "where": "task-b/04056b45"}], "files": 1, "skipped": None},
        "codex": {"items": [], "files": 0, "skipped": "已于 2026-09-01 毕业，§8 之后不再读卷"},
        "cast": {"items": [], "files": 0,
                 "skipped": "course 模式登录不录屏（§4.3 只测评录）—— hermes / codex 里的操作没有任何记录可查"},
    }
    out = me.render_module("s", mod, sources)
    assert "命中 1 处" in out and "hermes profile create" in out
    assert "② codex 会话  未读 —— 已于" in out
    assert "③ 录屏  未读 —— course 模式" in out
    assert "sandctl module s m3-hermes --state exempt" in out
    cap = me.render_module("s", me.module_of({"student": "s", "track": "B"}, "capstone"), sources)
    assert "毕业项目的交付物是 PR" in cap


def test_overview_counts_typed_and_printed_separately():
    mods = me.track_modules("B")
    sources = {
        "claude": {"items": [{"text": "pytest -q"}, {"text": "hermes profile"}], "files": 1, "skipped": None},
        "codex": {"items": [], "files": 0, "skipped": None},
        "cast": {"items": [{"kind": "敲", "text": "crontab -e"},
                           {"kind": "", "text": "cron: usage"}], "files": 1, "skipped": None},
    }
    out = me.render_overview("s", mods, sources)
    row = {l.split()[0]: l.split() for l in out.splitlines() if l.startswith(("m", "capstone"))}
    assert row["m5-quality"][1:5] == ["1", "0", "0", "0"]
    assert row["m7-auto"][1:5] == ["0", "0", "1", "1"]
    assert row["capstone"][1:5] == ["—", "—", "—", "—"]


def test_render_module_lists_typed_before_printed():
    mod = me.module_of({"student": "s", "track": "B"}, "m3-hermes")
    sources = {
        "claude": {"items": [], "files": 0, "skipped": None},
        "codex": {"items": [], "files": 0, "skipped": None},
        "cast": {"items": [{"when": "08-25 00:00:05", "kind": "", "text": "profile Manage profiles",
                            "where": "a.cast", "count": 1},
                           {"when": "08-25 00:00:09", "kind": "敲", "text": "hermes profile list",
                            "where": "a.cast", "count": 1}], "files": 1, "skipped": None},
    }
    out = me.render_module("s", mod, sources)
    assert "学员敲过 1 条 · 程序输出 1 行" in out
    assert out.index("hermes profile list") < out.index("── 输出里的") < out.index("profile Manage profiles")


def test_pad_counts_cjk_as_two_columns():
    assert me._pad("说", 4) == "说  "
    assert me._pad("ab", 4) == "ab  "


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {name}\n       {type(e).__name__}: {e}")
    print(f"\n通过 {len(tests) - failed}，失败 {failed}")
    sys.exit(1 if failed else 0)
