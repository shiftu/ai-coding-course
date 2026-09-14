"""llm-gateway 的管理面客户端。

网关是另一个项目：https://github.com/shiftu/llm-gateway ，本仓库不含它，
必须先跑起来。它没有管 key 的 CLI 子命令，但 MCP 端点走 HTTP JSON-RPC，
admin token 默认在 ~/.config/llm-gateway/token（MICROCLASS_GATEWAY_TOKEN_FILE 可改）。
这里只用标准库。

每人一把 key 是设计文档 §1.1 漏掉、spike 补上的工程项：
它同时是 §8「毕业即停止采集」的那个开关 —— 吊销 key，采集立刻停。
"""
import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("MICROCLASS_GATEWAY_ADMIN", "http://127.0.0.1:7421")
TOKEN_PATH = os.path.expanduser(
    os.environ.get("MICROCLASS_GATEWAY_TOKEN_FILE", "~/.config/llm-gateway/token"))
TEAM_SLUG = os.environ.get("MICROCLASS_TEAM", "microclass")

# 网关鉴权的内存缓存 TTL，见 llm-gateway internal/server/server.go:
#   cache := authpkg.NewKeyCache(60 * time.Second)
# 命中缓存时不查 DB，因此看不到 revoked_at；且每次鉴权成功都会 Put 一次、
# 把 expiresAt 重新推后。吊销要真正生效，必须先让这把 key 安静满一个 TTL。
AUTH_CACHE_TTL = 60


class GatewayError(RuntimeError):
    pass


def _token():
    try:
        with open(TOKEN_PATH) as f:
            return f.read().strip()
    except OSError as e:
        raise GatewayError(f"读不到网关 admin token（{TOKEN_PATH}）：{e}") from e


def _call(tool, arguments, base=DEFAULT_BASE, timeout=15):
    """调一个 MCP 工具，返回解析后的结果。"""
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }).encode()
    req = urllib.request.Request(
        f"{base}/mcp", data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise GatewayError(f"网关不可达（{base}）：{e}") from e

    if "error" in body:
        raise GatewayError(f"{tool} 失败：{body['error']}")
    try:
        text = body["result"]["content"][0]["text"]
    except (KeyError, IndexError) as e:
        raise GatewayError(f"{tool} 返回结构看不懂：{body}") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def healthy(base=DEFAULT_BASE, timeout=5):
    try:
        with urllib.request.urlopen(f"{base}/healthz", timeout=timeout) as r:
            return json.loads(r.read().decode()).get("status") == "ok"
    except Exception:
        return False


def ensure_team(slug=TEAM_SLUG, name="AI 微课堂"):
    for t in _call("list_teams", {}):
        if t.get("slug") == slug:
            return t["id"]
    return _call("add_team", {"slug": slug, "name": name})["id"]


def issue_student_key(student, slug=TEAM_SLUG):
    """给一名学员签一把 inbound key。明文只此一次，调用方必须立刻落盘。"""
    r = _call("issue_api_key", {
        "team_slug": slug, "scope": "inbound", "label": f"stu-{student}",
    })
    if not r.get("token"):
        raise GatewayError(f"签发没拿到明文 token：{r}")
    return r["key_id"], r["token"]


def revoke_key(key_id):
    return _call("revoke_api_key", {"key_id": key_id})


def key_record(key_id, slug=TEAM_SLUG):
    for k in _call("list_api_keys", {"team_slug": slug}):
        if k.get("id") == key_id:
            return k
    return None


def key_active(key_id, slug=TEAM_SLUG):
    """这把 key 在网关账面上还有效吗？

    注意别用「还在不在列表里」当判据 —— 吊销后它**仍然在列表里**，
    只是多了一个 revoked_at。用存在性判断会永远认为吊销失败。
    """
    k = key_record(key_id, slug)
    return bool(k) and not k.get("revoked_at")


def request_logs(key_id, limit=200):
    """按 key 拉这名学员的网关调用记录 —— 证据链四件套之一（§4.3）。"""
    return _call("list_request_logs", {"key_id": key_id, "limit": limit})
