"""录屏脱敏：学员证据目录里的 .cast → 可以给所有学员看的副本。

**只覆盖已知模式，不是闸。** 闸是挑选案例的人：入库前必须有人从头看一遍
（notes.md 模板的第一行就是这句）。这里每加一类泄露就加一条测试，
把已知模式钉死，未知的靠人。

纯函数：吃文本、吐文本和计数，不碰文件系统（redact_cast 除外，它只做读写）。
"""
import json
import re

REDACTED = "[REDACTED]"
STUDENT_PLACEHOLDER = "student"
HOST_PLACEHOLDER = "gateway.example"

# 已知的密钥形态。顺序有意义：先长后短，免得 Bearer 后面的 sk-… 被拆成两半各替一次。
_SECRET_PATTERNS = (
    # Authorization: Bearer xxx / "Bearer xxx"
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1" + REDACTED),
    # 各家 key 的常见前缀：sk-…（OpenAI/Anthropic 风格）、ak_…（网关 key id）
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), REDACTED),
    (re.compile(r"\bak_[A-Za-z0-9]{6,}"), REDACTED),
    # 环境变量 / .env 回显：KEY=value、KEY: value —— 只替值
    (re.compile(r"((?:ANTHROPIC_AUTH_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY|"
                r"[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD))\s*[=:]\s*)(?!\[REDACTED\])\S{6,}"),
     r"\1" + REDACTED),
    # 飞书 open_id
    (re.compile(r"\bou_[a-z0-9]{8,}"), REDACTED),
)

# 提示符里的主机名：root@mc-stu-x:~# → root@sandbox:~#
_PROMPT_HOST = re.compile(r"(\b[a-z_][a-z0-9_-]*@)[A-Za-z0-9._-]+(?=:)")


def redact_text(text, *, student, hosts=()):
    """一段终端输出 → (脱敏后的文本, {类别: 次数})。

    student：学员 ID，出现在提示符、标题、路径里，一律换成占位。
    hosts：额外要抹掉的主机/URL（网关、Gitea 地址），换成占位域名。
    """
    counts = {}

    def bump(k, n):
        if n:
            counts[k] = counts.get(k, 0) + n

    out = text
    for pat, rep in _SECRET_PATTERNS:
        out, n = pat.subn(rep, out)
        bump("secret", n)
    out, n = _PROMPT_HOST.subn(r"\1sandbox", out)
    bump("host", n)
    for h in hosts:
        if h:
            out, n = re.subn(re.escape(h), HOST_PLACEHOLDER, out)
            bump("host", n)
    if student:
        # 只替整词：学员 ID 可能很短（"s"），裸替会把 messages 改成 meStudentages。
        out, n = re.subn(r"(?<![A-Za-z0-9_])" + re.escape(student) + r"(?![A-Za-z0-9_])",
                         STUDENT_PLACEHOLDER, out)
        bump("student", n)
    return out, counts


def redact_header(header, *, student):
    """asciicast v2 头：title 里有学员 ID；env 里可能带 shell 之外的东西，只留白名单。"""
    h = dict(header)
    if isinstance(h.get("title"), str):
        h["title"], _ = redact_text(h["title"], student=student)
    env = h.get("env")
    if isinstance(env, dict):
        h["env"] = {k: v for k, v in env.items() if k in ("SHELL", "TERM")}
    return h


def redact_cast(src, dst, *, student, hosts=()):
    """整段录屏脱敏，逐事件处理，写到 dst。返回累计计数。

    一个密钥可能被终端拆成两个输出事件 —— 这种情况正则看不见，
    这是「脱敏器不是闸」的具体例子之一。
    """
    total = {}
    with open(src, encoding="utf-8", errors="replace") as f, \
            open(dst, "w", encoding="utf-8") as g:
        head = f.readline()
        try:
            header = json.loads(head)
        except json.JSONDecodeError:
            raise ValueError(f"{src} 不是 asciicast v2：第一行不是 JSON") from None
        if header.get("version") != 2:
            raise ValueError(f"{src} 不是 asciicast v2：version={header.get('version')!r}")
        g.write(json.dumps(redact_header(header, student=student), ensure_ascii=False) + "\n")
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                t, kind, payload = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue                    # 坏行直接丢，不让它带着原文进公开副本
            if isinstance(payload, str):
                payload, counts = redact_text(payload, student=student, hosts=hosts)
                for k, n in counts.items():
                    total[k] = total.get(k, 0) + n
            g.write(json.dumps([t, kind, payload], ensure_ascii=False) + "\n")
    return total
