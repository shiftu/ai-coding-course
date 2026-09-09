#!/usr/bin/env python3
"""签名 cookie 会话。没有会话表、没有 redis —— 100 人的规模不需要。

cookie 里放的是 `student|签发时间|HMAC`。服务端只验签名和时效，不存任何东西。
密钥落在状态目录下的一个 0600 文件里，随机生成，重启不变（否则每次重启
所有人被踢下线）。
"""
import base64
import hashlib
import hmac
import os
import secrets
import time

import sitepath  # noqa: F401  先把 control/ 挂进 sys.path
import store

COOKIE = "mc_session"
TTL = 12 * 3600          # 12 小时。一天的课够用，隔夜要重新登录。
_SECRET_PATH = os.path.join(store.STATE_DIR, "web-secret")


def secret():
    """读密钥；没有就生成一把。0600，和明文 key 一个待遇。"""
    try:
        with open(_SECRET_PATH, "rb") as f:
            data = f.read().strip()
            if len(data) >= 32:
                return data
    except FileNotFoundError:
        pass
    store.init_dirs()
    data = base64.urlsafe_b64encode(secrets.token_bytes(48))
    fd = os.open(_SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return data


def _sign(payload):
    return hmac.new(secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue(student):
    payload = f"{student}|{int(time.time())}"
    return f"{payload}|{_sign(payload)}"


def verify(token, *, now=None):
    """返回学员 id，或 None。任何一步不对都返回 None，不解释原因。"""
    if not token:
        return None
    parts = token.split("|")
    if len(parts) != 3:
        return None
    student, issued, sig = parts
    payload = f"{student}|{issued}"
    # compare_digest：防时序侧信道。这里成本为零，没有不用的理由。
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        issued = int(issued)
    except ValueError:
        return None
    if (now or time.time()) - issued > TTL:
        return None
    try:
        store.check_id(student)
    except store.StoreError:
        return None
    return student


def cookie_header(token, *, secure, max_age=TTL):
    bits = [f"{COOKIE}={token}", "Path=/", f"Max-Age={max_age}",
            "HttpOnly", "SameSite=Lax"]
    if secure:
        bits.append("Secure")
    return "; ".join(bits)


def clear_header(secure):
    return cookie_header("", secure=secure, max_age=0)


def read_cookie(header):
    """从 Cookie 头里取出我们那一条。"""
    for chunk in (header or "").split(";"):
        k, _, v = chunk.strip().partition("=")
        if k == COOKIE:
            return v
    return None
