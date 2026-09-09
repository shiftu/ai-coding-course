#!/usr/bin/env python3
"""对着**真的 ttyd** 验一遍反代。离线测试覆盖不到这一段。

会真的建一个容器（默认 web-probe），跑完删掉。要 docker + 网关健康。

    python3 live_probe.py [--student web-probe] [--keep]

验四件事：
  1. 直连容器端口不带认证 → 401（证明 basic auth 真的开着）
  2. 经过前端拿 /t/ → 200，且是 ttyd 的页面（证明前端替学员补上了认证）
  3. WebSocket 升级 → 101（终端是长连接，HTTP 通了不代表终端能用）
  4. 没登录的人走 /t/ → 401（反代不是一个开放的洞）
"""
import argparse
import base64
import pathlib
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import sitepath  # noqa: E402,F401
import sandbox   # noqa: E402
import serve     # noqa: E402
import store     # noqa: E402

CONTROL = sitepath.ROOT / "platform" / "control"
FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def sandctl(*args):
    return subprocess.run([sys.executable, str(CONTROL / "sandctl"), *args],
                          capture_output=True, text=True)


def raw(host, port, request, *, read=4096):
    with socket.create_connection((host, port), 10) as s:
        s.sendall(request.encode())
        s.settimeout(10)
        buf = b""
        try:
            while len(buf) < read:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\r\n\r\n" in buf:
                    break
        except (TimeoutError, OSError):
            pass
        return buf.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--student", default="web-probe")
    ap.add_argument("--keep", action="store_true", help="跑完不删容器")
    a = ap.parse_args()
    stu = a.student

    if store.exists(stu):
        sys.exit(f"错误：{stu} 已存在。先 sandctl destroy {stu}")

    print(f"建容器 {stu} …")
    r = sandctl("create", stu, "--mode", "assessment", "--track", "A")
    if r.returncode != 0:
        sys.exit(f"建不起来：{r.stderr or r.stdout}")
    try:
        rec = store.load(stu)
        port, bp = rec["ttyd_port"], sandbox.TTYD_BASE_PATH
        print(f"  容器 {rec['container']}，ttyd 127.0.0.1:{port}{bp}/\n")

        print("== 1. 直连容器端口 ==")
        resp = raw("127.0.0.1", port, f"GET {bp}/ HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        check("不带认证直连 → 401", "401" in resp.split("\r\n")[0], resp.split("\r\n")[0])
        cred = base64.b64encode(f"{rec['ttyd_user']}:{rec['ttyd_password']}".encode()).decode()
        resp = raw("127.0.0.1", port,
                   f"GET {bp}/ HTTP/1.1\r\nHost: x\r\nAuthorization: Basic {cred}\r\n"
                   f"Connection: close\r\n\r\n")
        check("带认证直连 → 200", "200" in resp.split("\r\n")[0], resp.split("\r\n")[0])
        resp = raw("127.0.0.1", port,
                   f"GET / HTTP/1.1\r\nHost: x\r\nAuthorization: Basic {cred}\r\n"
                   f"Connection: close\r\n\r\n")
        check(f"根路径不再提供服务（ttyd 挂在 {bp} 下）",
              "404" in resp.split("\r\n")[0], resp.split("\r\n")[0])

        print("\n== 2. 起前端 ==")
        sandctl("bind", stu, "--lark-open-id", f"ou_probe_{stu}")
        serve.Handler.dev_login = True
        srv = serve.Server(("127.0.0.1", 0), serve.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        wport = srv.server_address[1]
        print(f"  http://127.0.0.1:{wport}")

        resp = raw("127.0.0.1", wport, f"GET {bp}/ HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        check("没登录走反代 → 401", "401" in resp.split("\r\n")[0], resp.split("\r\n")[0])

        req = urllib.request.Request(f"http://127.0.0.1:{wport}/auth/dev",
                                     data=f"student={stu}".encode(), method="POST")
        class NoRedir(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *x, **k):
                return None
        op = urllib.request.build_opener(NoRedir)
        try:
            op.open(req, timeout=10)
            cookie = ""
        except urllib.error.HTTPError as e:
            cookie = (e.headers.get("Set-Cookie") or "").split(";")[0]
        check("开发登录拿到 cookie", cookie.startswith("mc_session="), cookie[:24])

        print("\n== 3. 经过前端拿终端页 ==")
        resp = raw("127.0.0.1", wport,
                   f"GET {bp}/ HTTP/1.1\r\nHost: x\r\nCookie: {cookie}\r\n"
                   f"Connection: close\r\n\r\n", read=65536)
        line = resp.split("\r\n")[0]
        check("反代 → 200", "200" in line, line)
        check("拿到的是 ttyd 的页面", "ttyd" in resp.lower() or "<html" in resp.lower(),
              resp[:80].replace("\r\n", " "))

        print("\n== 4. WebSocket 升级 ==")
        ws = (f"GET {bp}/ws HTTP/1.1\r\nHost: 127.0.0.1:{wport}\r\nCookie: {cookie}\r\n"
              f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
              f"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: tty\r\n"
              f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n")
        resp = raw("127.0.0.1", wport, ws)
        line = resp.split("\r\n")[0]
        check("升级 → 101 Switching Protocols", "101" in line, line)
        check("回了 Sec-WebSocket-Accept", "sec-websocket-accept" in resp.lower(),
              "" if "sec-websocket-accept" in resp.lower() else resp[:120].replace("\r\n", " "))

        srv.shutdown()
        srv.server_close()
    finally:
        if not a.keep:
            print(f"\n清理 {stu} …")
            print(" ", sandctl("destroy", stu).stdout.strip().replace("\n", "\n  "))

    print(f"\n{'全部通过' if not FAILS else str(len(FAILS)) + ' 条不符：' + '、'.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
