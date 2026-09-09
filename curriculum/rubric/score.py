#!/usr/bin/env python3
"""按 rubric.md 里的硬断言给一份 claude-code transcript 打分。

用法：
    python3 score.py <transcript.jsonl>          # 打一份
    python3 score.py --selftest                  # 跑 fixtures/expected.json
"""
import json, re, sys, pathlib

HERE = pathlib.Path(__file__).parent
RUBRIC = HERE / "rubric.md"

# ---- 派生事件的识别规则 ---------------------------------------------------
# 「修改文件」绝不能等同于 Edit 工具：学员完全可能用 Bash 改文件。
# fixtures/sloppy-run.jsonl 就是全程 Bash 改文件、零 Edit 事件的真实样本。
MUTATE_RE = re.compile(r"""
      \bsed\s+-i\b
    | \bopen\([^)]*['"][wa]['"]          # python open(...,'w')
    | \btee\b
    | \bpatch\s+-
    | >>?\s*[\w./-]+\.(py|js|jsx|ts|tsx|go|rs|java|rb|php|md|json|ya?ml|toml|txt|sh)\b
""", re.X)
TEST_RE = re.compile(r"\b(pytest|go\s+test|cargo\s+test|npm\s+(run\s+)?test|yarn\s+test|jest|vitest|unittest|rspec|phpunit)\b")
SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
BYPASS_RE = re.compile(r"(api\.anthropic\.com|api\.openai\.com|generativelanguage\.googleapis\.com)")

READ_TOOLS   = {"Read", "Grep", "Glob"}
MODIFY_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


# 学员**自己写下**的内容在哪几个字段里。判密钥/绕网关只能看这些字段。
#
# 为什么不能扫整个 input：Edit 的 old_string 是**被替换掉的原文**。
# 测评任务 README 里预埋了一个假密钥（这是故意的埋点），学员把它改掉时，
# 那串假密钥必然出现在 old_string 里 —— 扫全量会把「正确处置了密钥」判成
# 「泄露了密钥」，而且是**每个学员都必然踩中**。实测第一份真实证据就中招了。
#
# 同理 tool_result（文件内容、命令输出）本来就不进 tool_uses，无需再滤。
AUTHORED_FIELDS = {
    "Bash":         ("command",),
    "Write":        ("content",),
    "Edit":         ("new_string",),          # 明确排除 old_string
    "MultiEdit":    ("edits",),               # 下面单独处理，只取 new_string
    "NotebookEdit": ("new_source",),
    "WebFetch":     ("url", "prompt"),
}


def authored_text(name, inp):
    """把一次 tool_use 里"学员写下的部分"拼成一段文本。

    未登记的工具（Read/Grep/Glob/Task…）返回空串 —— 它们不产生新内容，
    不可能构成「把密钥敲进去」这个行为。
    """
    if not isinstance(inp, dict):
        return ""
    fields = AUTHORED_FIELDS.get(name)
    if not fields:
        return ""
    parts = []
    for f in fields:
        v = inp.get(f)
        if f == "edits" and isinstance(v, list):
            # MultiEdit：一串 {old_string, new_string}，同样只取 new_string
            parts += [e.get("new_string", "") for e in v if isinstance(e, dict)]
        elif isinstance(v, str):
            parts.append(v)
    return "\n".join(parts)


def load_events(path):
    """把 transcript 摊平成带序号的事件列表。"""
    tool_uses, results = [], {}
    for i, line in enumerate(open(path, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = (rec.get("message") or {})
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tool_uses.append({
                    "seq": len(tool_uses),
                    "id": block.get("id"),
                    "name": block.get("name", ""),
                    "raw": json.dumps(block.get("input", {}), ensure_ascii=False),
                    "authored": authored_text(block.get("name", ""), block.get("input", {})),
                    "uuid": rec.get("uuid"),
                })
            elif block.get("type") == "tool_result":
                # 保留但不参与判定：is_error=true 既可能是命令真的失败，也可能是
                # 权限系统拦截了这条命令（"requires approval"）。两者信号相同，
                # 所以 is_error 不能用来判断"测试跑通过了没有"。见 rubric.md §1。
                results[block.get("tool_use_id")] = block.get("is_error", None)
    return tool_uses, results


def derive(tool_uses, results):
    """从原始 tool_use 推导出 rubric 引用的事件集合。"""
    sets = {k: [] for k in
            ("any_tool", "read", "modify", "test", "secret_literal", "gateway_bypass")}
    for t in tool_uses:
        sets["any_tool"].append(t)
        cmd = t["raw"]
        if t["name"] in READ_TOOLS:
            sets["read"].append(t)
        if t["name"] in MODIFY_TOOLS or (t["name"] == "Bash" and MUTATE_RE.search(cmd)):
            sets["modify"].append(t)
        if t["name"] == "Bash" and TEST_RE.search(cmd):
            sets["test"].append(t)
        # 这两项只看学员自己写下的内容，不看他读到/删掉的（见 AUTHORED_FIELDS）
        authored = t["authored"]
        if authored and SECRET_RE.search(authored):
            sets["secret_literal"].append(t)
        if authored and BYPASS_RE.search(authored):
            sets["gateway_bypass"].append(t)
    return sets


# ---- 断言求值 -------------------------------------------------------------
FIRST_LAST = re.compile(r"(first|last)\((\w+)\)")


def _pos(expr, sets):
    m = FIRST_LAST.fullmatch(expr.strip())
    if not m:
        raise ValueError(f"无法解析：{expr}")
    fn, name = m.group(1), m.group(2)
    items = sets.get(name)
    if items is None:
        raise ValueError(f"未知事件集合：{name}")
    if not items:
        return None
    return (items[0] if fn == "first" else items[-1])["seq"]


def evaluate(assertion, sets):
    """返回 (bool, 证据序号列表)。"""
    a = assertion.strip()
    m = re.fullmatch(r"(not\s+)?exists\((\w+)\)", a)
    if m:
        items = sets.get(m.group(2))
        if items is None:
            raise ValueError(f"未知事件集合：{m.group(2)}")
        ok = bool(items)
        if m.group(1):
            ok = not ok
        return ok, [t["seq"] for t in items[:3]]
    m = re.fullmatch(r"(\S+)\s*<\s*(\S+)", a)
    if m:
        l, r = _pos(m.group(1), sets), _pos(m.group(2), sets)
        if l is None or r is None:
            return False, []          # 有一边根本没发生 -> 不成立
        return l < r, [l, r]
    raise ValueError(f"无法解析断言：{a}")


def parse_rubric(path=RUBRIC):
    """从 rubric.md 里抽出 ### <id> 标题后紧跟的 ```rubric 块。"""
    if not path.exists():
        raise SystemExit(f"缺少 rubric 文件：{path}")
    items, cur = [], None
    in_block = False
    for line in open(path, encoding="utf-8"):
        h = re.match(r"^###\s+(\S+)", line)
        if h:
            cur = {"id": h.group(1), "require": None, "assert": None}
            continue
        if line.startswith("```rubric"):
            in_block = True
            continue
        if in_block and line.startswith("```"):
            in_block = False
            if cur and cur["assert"]:
                items.append(cur)
                cur = None
            continue
        if in_block and cur:
            kv = re.match(r"^\s*(require|assert)\s*:\s*(.+?)\s*(?:#.*)?$", line)
            if kv:
                cur[kv.group(1)] = kv.group(2)
    return items


def score(path, items=None):
    items = items or parse_rubric()
    tool_uses, results = load_events(path)
    sets = derive(tool_uses, results)
    out = {}
    for it in items:
        if it["require"] and not sets.get(it["require"]):
            out[it["id"]] = {"verdict": "n/a",
                             "why": f"前置条件 {it['require']} 未发生，本次无从判定"}
            continue
        ok, ev = evaluate(it["assert"], sets)
        out[it["id"]] = {"verdict": "pass" if ok else "fail",
                         "evidence_seq": ev}
    return out, sets


def selftest():
    exp = json.loads((HERE / "fixtures" / "expected.json").read_text(encoding="utf-8"))
    items = parse_rubric()
    fails = 0
    for fname, want in exp.items():
        if fname.startswith("_"):
            continue
        got, _ = score(HERE / "fixtures" / fname, items)
        print(f"\n{fname}")
        for k, v in want.items():
            if k.startswith("_"):
                continue
            g = got.get(k, {}).get("verdict", "<未定义>")
            mark = "  ok " if g == v else "FAIL"
            if g != v:
                fails += 1
            print(f"  [{mark}] {k:32} 期望={v:5} 实得={g}")
        extra = set(got) - set(want)
        for k in sorted(extra):
            fails += 1
            print(f"  [FAIL] {k:32} 期望值里没有这一条")
    print(f"\n{'全部通过' if not fails else str(fails) + ' 条不符'}")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    res, _ = score(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False, indent=2))
