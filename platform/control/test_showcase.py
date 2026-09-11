#!/usr/bin/env python3
"""showcase 的离线测试：入库、结构校验、路径穿越。

不碰 docker、不碰真仓库：SHOWCASE_DIR 和 MICROCLASS_STATE 都指到临时目录。
跑法：python3 test_showcase.py
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="mc-showcase-test-")
os.environ["MICROCLASS_STATE"] = os.path.join(TMP, "state")       # 必须在 import store 之前
os.environ["MICROCLASS_SHOWCASE"] = os.path.join(TMP, "showcase")
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import showcase  # noqa: E402
import store     # noqa: E402

STUDENT = "stu-x"


def _seed_cast(name="session.cast"):
    p = pathlib.Path(store.evidence_dir(STUDENT)) / name
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"version": 2, "width": 120, "height": 32, "title": "microclass/stu-x"}) + "\n")
        f.write(json.dumps([0.5, "o", "root@mc-stu-x:~# export OPENAI_API_KEY=sk-abcdefghijklmnop\r\n"]) + "\n")
        f.write(json.dumps([1.0, "o", "hermes profile list\r\n"]) + "\n")
    return p


def _add(slug="memory-verify", **kw):
    args = dict(module="m3-hermes", verdict="good", title="新会话验证记忆生效",
                slug=slug, by="panda")
    args.update(kw)
    return showcase.add_case(STUDENT, "session.cast", **args)


def test_add_case_writes_redacted_copy_and_metadata():
    _seed_cast()
    d, counts = _add()
    assert d == showcase.SHOWCASE_DIR / "m3-hermes" / "good-memory-verify"
    cast = (d / showcase.CAST_NAME).read_text(encoding="utf-8")
    assert "stu-x" not in cast and "sk-" not in cast
    assert "hermes profile list" in cast
    assert counts == {"host": 1, "secret": 1}
    meta = showcase.parse_case(d / showcase.CASE_YAML)
    assert meta == {"module": "m3-hermes", "verdict": "good", "title": "新会话验证记忆生效",
                    "source": "student", "picked_by": "panda"}
    assert "入库前必须有人从头看一遍" in (d / showcase.NOTES_MD).read_text(encoding="utf-8")
    # 原文件一个字节没动
    assert "sk-abcdefghijklmnop" in _seed_src().read_text(encoding="utf-8")
    shutil.rmtree(d)


def _seed_src():
    return pathlib.Path(store.evidence_dir(STUDENT)) / "session.cast"


def test_add_case_refuses_unknown_module_bad_slug_and_duplicates():
    _seed_cast()
    for kw, needle in ((dict(module="m99-nope"), "不在任何轨道"),
                       (dict(slug="../x"), "slug"),
                       (dict(verdict="meh"), "verdict"),
                       (dict(source="bot"), "source")):
        try:
            _add(**kw)
        except showcase.ShowcaseError as e:
            assert needle in str(e), str(e)
        else:
            raise AssertionError(f"{kw} 应该被拒")
    d, _ = _add()
    try:
        _add()
    except showcase.ShowcaseError as e:
        assert "已存在" in str(e)
    else:
        raise AssertionError("重复入库应该被拒")
    shutil.rmtree(d)


def test_add_case_refuses_cast_outside_student_dir():
    _seed_cast()
    for evil in ("../other/session.cast", "notes.txt"):
        try:
            showcase.add_case(STUDENT, evil, module="m3-hermes", verdict="bad",
                              title="t", slug="evil", by="x")
        except showcase.ShowcaseError:
            pass
        else:
            raise AssertionError(f"{evil} 应该被拒")


def test_check_case_flags_template_notes_and_bad_cast():
    _seed_cast()
    d, _ = _add(slug="check")
    errs = showcase.check_case(showcase.parse_case(d / showcase.CASE_YAML), d,
                               known_modules=showcase.all_modules())
    assert errs == [f"{showcase.NOTES_MD} 还带着模板里的复核提示 —— 看完录屏再把它删掉"]
    (d / showcase.NOTES_MD).write_text("## 看什么\n\n先看测试再改代码。\n", encoding="utf-8")
    (d / showcase.CAST_NAME).write_text('{"version":2,"width":0}\n', encoding="utf-8")
    errs = showcase.check_case(showcase.parse_case(d / showcase.CASE_YAML), d,
                               known_modules=showcase.all_modules())
    assert len(errs) == 1 and "可回放" in errs[0]
    shutil.rmtree(d)


def test_load_and_list_reject_traversal_and_group_by_module():
    _seed_cast()
    d1, _ = _add(slug="a")
    d2, _ = _add(slug="b", verdict="bad")
    assert showcase.load_case("m3-hermes", "../m3-hermes") is None
    assert showcase.load_case("..", "good-a") is None
    assert showcase.load_case("m3-hermes", "nope") is None
    c = showcase.load_case("m3-hermes", "good-a")
    assert c and c["title"] == "新会话验证记忆生效" and c["has_cast"]
    grouped = showcase.list_cases()
    assert list(grouped) == ["m3-hermes"]
    assert [x["slug"] for x in grouped["m3-hermes"]] == ["good-a", "bad-b"]   # good 在前
    shutil.rmtree(d1)
    shutil.rmtree(d2)


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
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {len(tests) - failed}，失败 {failed}")
    sys.exit(1 if failed else 0)
