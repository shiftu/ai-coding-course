#!/usr/bin/env python3
"""spec/scope-control 的 llm 判定。

只读**学员说的话**（transcript 里 type=="user" 且 content 为字符串的记录），
不看 agent 的工具调用 —— 工具调用反映的是 agent 的默认行为，不是学员的表达。

用法：
    python3 judge.py <transcript.jsonl>                 # 默认按任务 A 判
    python3 judge.py --task b <transcript.jsonl>        # 按轨道 B 的歧义清单判
    python3 judge.py --render b                         # 只看渲染出的 prompt，不打网络
    python3 judge.py --selftest              # 跑 fixtures/spec/expected.json
    python3 judge.py --consistency 3         # 自洽性：同一输入连跑 N 次看结论是否一致

**--task 决定拿哪份歧义清单去问模型**（见 ../assessment/scope/）。用错了不会报错，
会得到一份格式合法、引用真实、结论全错的判定 —— 所以结果 JSON 里始终带 task 字段，
批改时能一眼看出是按哪个变体判的。
"""
import json
import os
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).parent
GATEWAY = os.environ.get("LLM_GATEWAY_URL", "http://127.0.0.1:7421")
MODEL = os.environ.get("JUDGE_MODEL", "charaboard/claude-sonnet-5")
# 网关（https://github.com/shiftu/llm-gateway）的 admin token。
# 和 platform/control/gateway.py 认同一个文件、同一个环境变量。
TOKEN_FILE = pathlib.Path(os.path.expanduser(
    os.environ.get("MICROCLASS_GATEWAY_TOKEN_FILE", "~/.config/llm-gateway/token")))

# 少于这个数量的学员发言 = 只有初始任务描述，没有可判定的表达行为
MIN_TURNS_TO_JUDGE = 2

PROMPT = """你在评估一名学员在 AI 结对编程测评中的**需求表达**能力。

下面是该学员在会话中说的每一句话，按顺序排列，每条带一个 uuid。
这些是学员**打给 AI 的字**，不包含 AI 的行为。

{task_block}

判定标准：
- pass：至少做到第 3 点或第 4 点。evidence 引用**体现范围控制的那几句原话**。
- fail：通篇只是转述任务或催促，四点都没有。
  注意 fail 的证据是「缺席」——没有范围表述可引。这时 evidence 请引用**学员发言中
  最有代表性的 2–3 句**（例如纯催促、纯转述的那几句），用来证明"他说的就是这些，
  其中不含任何范围表述"。**fail 也必须给 evidence，不能留空。**
- n/a：材料确实不足以判断（发言过少、或全部与任务无关）。
  **宁可判 n/a，不要凭印象判 fail。**

只输出 JSON，不要任何其他文字，格式：
{{"verdict":"pass|fail|n/a","evidence":[{{"uuid":"<原文 uuid>","quote":"<原话片段>"}}],"reasoning":"<一句话理由>"}}

evidence 里的 uuid **必须逐字取自下面材料**，禁止改写或编造。
只有在判 n/a 时 evidence 才允许为空数组；pass 和 fail 都必须给出至少一条引用。

学员发言：
{turns}
"""


SCOPE_DIR = HERE.parent / "assessment" / "scope"


def load_scope(task):
    """读某个变体的歧义清单。

    这块内容原先写死在 PROMPT 里，是任务 A 专用的。拿它去判轨道 B 的学员，
    模型会照着「最近一周」「活跃贡献者」去找 —— 而 B 的 Issue 里压根没这两个词，
    于是稳定地判 fail，**且判定看起来完全合法**（格式对、引用真实、理由通顺）。
    比报错更糟的就是这种：错得像对的。
    """
    path = SCOPE_DIR / f"{task}.json"
    if not path.is_file():
        raise SystemExit(
            f"没有任务 {task!r} 的范围规格（找不到 {path}）。"
            f"现有：{sorted(p.stem for p in SCOPE_DIR.glob('*.json'))}")
    return json.loads(path.read_text(encoding="utf-8"))


def render_task_block(scope):
    """把规格渲染成 PROMPT 里那段「任务埋了什么 + 判据」。"""
    ambs = scope["ambiguities"]
    lines = [f"测评任务本身埋了{'两' if len(ambs) == 2 else len(ambs)}处歧义和一处超量："]
    lines += [f"- {a['issue_line']}；" for a in ambs]
    lines.append(f"- {scope['overload_line']}。")
    lines.append("")
    lines.append("请判定这名学员是否做到了**范围控制**，判据是以下四点：")
    for i, a in enumerate(ambs, 1):
        lines.append(f"{i}. {a['criterion']}；")
    n = len(ambs)
    lines.append(f"{n + 1}. 识别之后，是否**明确说出**自己按哪种理解处理"
                 "（静默按某种理解做 = 未做到）；")
    lines.append(f"{n + 2}. 面对做不完的任务量，是否讲清了「这次做了什么、哪些没做、为什么」。")
    return "\n".join(lines)


def extract_student_turns(path):
    """学员的话 = type=="user" 且 message.content 是字符串。

    tool_result 也是 type=="user"，但 content 是数组 —— 必须排除，
    否则会把工具输出当成学员的表达来评分。
    """
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") != "user":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            out.append({"uuid": rec.get("uuid", ""), "text": content.strip()})
    return out


def _call_gateway(prompt):
    token = TOKEN_FILE.read_text().strip()
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GATEWAY}/v1/messages", data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in payload.get("content", []))


def _parse_json(raw):
    """模型有时会用 ``` 包住 JSON，剥掉再解析。"""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.S)
    m = re.search(r"\{.*\}", s, re.S)
    return json.loads(m.group(0) if m else s)


def judge(path, task="a"):
    scope = load_scope(task)
    turns = extract_student_turns(path)
    if len(turns) < MIN_TURNS_TO_JUDGE:
        return {"task": task, "verdict": "n/a", "evidence": [],
                "reasoning": f"学员发言仅 {len(turns)} 条，没有可判定的表达行为",
                "guard": "skipped-no-api-call"}

    rendered = "\n".join(f'[uuid={t["uuid"]}] {t["text"]}' for t in turns)
    try:
        raw = _call_gateway(PROMPT.format(
            task_block=render_task_block(scope), turns=rendered))
        result = _parse_json(raw)
    except Exception as exc:                      # 网络/解析失败一律判 n/a，不猜
        return {"task": task, "verdict": "n/a", "evidence": [],
                "reasoning": f"判定调用失败：{type(exc).__name__}: {exc}",
                "guard": "call-failed"}

    # ---- 幻觉硬闸：引用的 uuid 必须真实存在于学员发言里 ----
    valid = {t["uuid"] for t in turns}
    cited = [e.get("uuid", "") for e in result.get("evidence", []) or []]
    bogus = [u for u in cited if u not in valid]
    if bogus:
        return {"task": task, "verdict": "n/a", "evidence": [],
                "reasoning": f"判定引用了不存在的 uuid {bogus}，整条判定作废",
                "guard": "bogus-uuid"}
    if result.get("verdict") in ("pass", "fail") and not cited:
        return {"task": task, "verdict": "n/a", "evidence": [],
                "reasoning": "判定未给出任何证据引用，按规则作废",
                "guard": "no-evidence"}

    result["task"] = task
    result["guard"] = "ok"
    return result


def selftest(rounds=1):
    exp = json.loads((HERE / "fixtures" / "spec" / "expected.json").read_text(encoding="utf-8"))
    fails = 0
    for fname, want in exp.items():
        if fname.startswith("_"):
            continue
        got = [judge(HERE / "fixtures" / "spec" / fname, task="a")
               for _ in range(rounds)]
        verdicts = [g["verdict"] for g in got]
        ok = all(v == want["verdict"] for v in verdicts)
        stable = len(set(verdicts)) == 1
        if not ok:
            fails += 1
        mark = "  ok " if ok else "FAIL"
        extra = "" if stable else "  ⚠ 不自洽"
        print(f"  [{mark}] {fname:22} 期望={want['verdict']:5} 实得={','.join(verdicts)}"
              f"  guard={got[0].get('guard')}{extra}")
        if not stable:
            fails += 1
        if got[0].get("evidence"):
            print(f"         证据: {got[0]['evidence'][0].get('uuid')} — "
                  f"{str(got[0]['evidence'][0].get('quote'))[:50]}")
    print(f"\n  {'全部通过' if not fails else str(fails) + ' 项不符'}")
    return 1 if fails else 0


def _arg(flag, default=None):
    """取 --flag 的值。没有就给默认。"""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


if __name__ == "__main__":
    task = _arg("--task", "a")
    if "--render" in sys.argv:                      # 只渲染 prompt，不打网络
        print(render_task_block(load_scope(_arg("--render", task))))
        sys.exit(0)
    if "--selftest" in sys.argv or "--consistency" in sys.argv:
        n = 1
        if "--consistency" in sys.argv:
            n = int(_arg("--consistency", "1"))
        print(f"  （每份 fixture 跑 {n} 次）\n")
        sys.exit(selftest(n))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    args = [a for a in args if a != task]           # --task 的值不是文件名
    if not args:
        sys.exit(__doc__)
    print(json.dumps(judge(args[0], task=task), ensure_ascii=False, indent=2))
