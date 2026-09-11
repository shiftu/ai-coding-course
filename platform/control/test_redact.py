#!/usr/bin/env python3
"""redact 的离线测试：每一类已知泄露一条用例，把「已知」钉死。

跑法：python3 test_redact.py
"""
import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import redact  # noqa: E402

TMP = tempfile.mkdtemp(prefix="mc-redact-test-")


def test_student_id_everywhere():
    out, c = redact.redact_text("root@mc-stu-x:/workspace# echo stu-x done", student="stu-x")
    assert "stu-x" not in out
    assert out == "root@sandbox:/workspace# echo student done"
    assert c == {"student": 1, "host": 1}


def test_bearer_and_sk_keys():
    out, c = redact.redact_text(
        'curl -H "Authorization: Bearer sk-abcdefghijklmnop" x; export OPENAI_API_KEY=sk-zzzzzzzzzzzz',
        student="s")
    assert "sk-" not in out
    assert out.count(redact.REDACTED) == 2
    assert c["secret"] == 2


def test_env_style_secret_values_only_value_is_replaced():
    out, _ = redact.redact_text("ANTHROPIC_AUTH_TOKEN=abcdef123456 GATEWAY_PASSWORD: hunter2x",
                                student="s")
    assert out == f"ANTHROPIC_AUTH_TOKEN={redact.REDACTED} GATEWAY_PASSWORD: {redact.REDACTED}"


def test_gateway_key_id_and_lark_open_id():
    out, _ = redact.redact_text("key ak_9f8e7d6c5b bound to ou_1234567890abcdef", student="s")
    assert "ak_" not in out and "ou_" not in out


def test_hosts_are_replaced_with_placeholder():
    out, c = redact.redact_text("POST http://host.docker.internal:7421/v1/messages",
                                student="s", hosts=("host.docker.internal:7421",))
    assert out == f"POST http://{redact.HOST_PLACEHOLDER}/v1/messages"
    assert c["host"] == 1


def test_short_student_id_is_matched_as_whole_word_only():
    out, c = redact.redact_text("messages from s in sandbox", student="s")
    assert out == "messages from student in sandbox"    # messages / sandbox 里的 s 不动
    assert c == {"student": 1}


def test_short_values_are_left_alone():
    # 5 位以内的「密钥」多半是误伤（PORT=7900 这种），不动
    out, c = redact.redact_text("PORT=7900 TOKEN=ab12", student="s")
    assert out == "PORT=7900 TOKEN=ab12" and c == {}


def test_redact_cast_rewrites_header_and_events():
    src = os.path.join(TMP, "a.cast")
    dst = os.path.join(TMP, "a-public.cast")
    with open(src, "w", encoding="utf-8") as f:
        f.write(json.dumps({"version": 2, "width": 120, "height": 32,
                            "title": "microclass/stu-x",
                            "env": {"SHELL": "/bin/bash", "TERM": "xterm", "HOME": "/workspace"}}) + "\n")
        f.write(json.dumps([0.1, "o", "root@mc-stu-x:~# cat /evidence/stu-x.cast .env\r\n"]) + "\n")
        f.write(json.dumps([0.2, "o", "OPENAI_API_KEY=sk-1234567890abcdef\r\n"]) + "\n")
        f.write("this line is broken\n")
        f.write(json.dumps([0.3, "r", "120x32"]) + "\n")
    counts = redact.redact_cast(src, dst, student="stu-x")

    lines = pathlib.Path(dst).read_text(encoding="utf-8").splitlines()
    head = json.loads(lines[0])
    assert head["title"] == "microclass/student"
    assert head["env"] == {"SHELL": "/bin/bash", "TERM": "xterm"}
    assert head["width"] == 120
    events = [json.loads(x) for x in lines[1:]]
    assert len(events) == 3                       # 坏行被丢掉
    assert "stu-x" not in lines[1] and "sk-" not in lines[2]
    assert events[2] == [0.3, "r", "120x32"]      # 非输出事件原样
    assert counts == {"student": 1, "host": 1, "secret": 1}


def test_redact_cast_rejects_non_v2():
    src = os.path.join(TMP, "bad.cast")
    pathlib.Path(src).write_text('{"version":1}\n', encoding="utf-8")
    try:
        redact.redact_cast(src, os.path.join(TMP, "bad-out.cast"), student="s")
    except ValueError as e:
        assert "v2" in str(e)
    else:
        raise AssertionError("v1 应该被拒")


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
