#!/usr/bin/env python3
"""judge.py 防幻觉 guard 的离线测试 —— 不打网络，直接替换网关调用。

guard 是整个 llm 判定的安全机制；正常样本跑通时它不会触发，
所以必须单独构造场景验证它真的会拦。
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import judge  # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures" / "spec" / "spec-weak.jsonl"
CASES = [
    ("编造的 uuid",        {"verdict": "fail", "evidence": [{"uuid": "w-999", "quote": "x"}]}, "bogus-uuid"),
    ("真假 uuid 混用",      {"verdict": "fail", "evidence": [{"uuid": "w-001", "quote": "x"},
                                                          {"uuid": "deadbeef", "quote": "y"}]}, "bogus-uuid"),
    ("pass 但无证据",       {"verdict": "pass", "evidence": []},                                "no-evidence"),
    ("fail 但无证据",       {"verdict": "fail", "evidence": []},                                "no-evidence"),
    ("引用 tool_result",   {"verdict": "fail", "evidence": [{"uuid": "w-002", "quote": "ok"}]}, "bogus-uuid"),
    ("合法引用",           {"verdict": "fail", "evidence": [{"uuid": "w-001", "quote": "x"}]}, "ok"),
    ("模型返回非 JSON",     "这不是 JSON",                                                      "call-failed"),
]

def main():
    original = judge._call_gateway
    fails = 0
    for name, fake, want_guard in CASES:
        judge._call_gateway = (lambda _p, f=fake: f if isinstance(f, str)
                               else json.dumps(f, ensure_ascii=False))
        got = judge.judge(FIX)
        ok = got.get("guard") == want_guard
        if not ok:
            fails += 1
        print(f"  [{'  ok ' if ok else 'FAIL'}] {name:18} 期望 guard={want_guard:16} "
              f"实得={got.get('guard')}  verdict={got.get('verdict')}")
    judge._call_gateway = original
    print(f"\n  {'guard 全部生效' if not fails else str(fails) + ' 项未按预期拦截'}")
    return 1 if fails else 0

if __name__ == "__main__":
    sys.exit(main())
