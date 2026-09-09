#!/usr/bin/env python3
"""飞书 SSO（OAuth 2.0 授权码）。只用标准库。

三步：跳转授权页 → 回调拿 code → 换 user_access_token → 读 open_id。
拿到 open_id 就结束了 —— 平台**不存**姓名、头像、部门这些东西，
只把 open_id 和一个已经存在的学员档案对上号（见 §8 隐私硬边界）。

端点可以用环境变量改，因为飞书国际版（larksuite.com）和自建域名不同。
"""
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request

APP_ID = os.environ.get("MICROCLASS_LARK_APP_ID", "")
APP_SECRET = os.environ.get("MICROCLASS_LARK_APP_SECRET", "")
AUTH_HOST = os.environ.get("MICROCLASS_LARK_AUTH_HOST", "https://accounts.feishu.cn")
API_HOST = os.environ.get("MICROCLASS_LARK_API_HOST", "https://open.feishu.cn")
TIMEOUT = 10


class SSOError(RuntimeError):
    pass


def configured():
    return bool(APP_ID and APP_SECRET)


def new_state():
    return secrets.token_urlsafe(24)


def authorize_url(redirect_uri, state):
    q = urllib.parse.urlencode({
        "client_id": APP_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    })
    return f"{AUTH_HOST}/open-apis/authen/v1/authorize?{q}"


def _post_json(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    return _send(req)


def _send(req):
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise SSOError(f"飞书接口 {e.code}：{body}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise SSOError(f"飞书接口不可达：{e}") from None


def exchange(code, redirect_uri):
    """授权码换 user_access_token。"""
    data = _post_json(f"{API_HOST}/open-apis/authen/v2/oauth/token", {
        "grant_type": "authorization_code",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
    })
    # v2 成功时 code=0；有些网关会把它放在 HTTP 200 里返回错误码，所以必须显式查。
    if data.get("code") not in (0, None):
        raise SSOError(f"换 token 失败：{data.get('error_description') or data}")
    token = data.get("access_token")
    if not token:
        raise SSOError(f"换 token 失败：响应里没有 access_token（{data}）")
    return token


def open_id(user_access_token):
    """只取 open_id。**故意不取姓名和邮箱** —— 平台不需要，也就不该拿。"""
    req = urllib.request.Request(
        f"{API_HOST}/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {user_access_token}"})
    data = _send(req)
    if data.get("code") != 0:
        raise SSOError(f"读用户信息失败：{data.get('msg') or data}")
    oid = (data.get("data") or {}).get("open_id")
    if not oid:
        raise SSOError("读用户信息失败：响应里没有 open_id")
    return oid
