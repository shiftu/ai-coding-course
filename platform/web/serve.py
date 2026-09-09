#!/usr/bin/env python3
"""microclass-web —— 学员的 5 个页面。

    python3 serve.py [--port 7900] [--host 127.0.0.1] [--dev-login]

只用标准库：没有构建步骤、没有 node_modules、没有框架版本要跟。
100 人/年的内部平台，多一条工具链就多一样会腐烂的东西。

对外请用 nginx/Caddy 做 TLS 终止再反代到这里，并把 X-Forwarded-Proto 传进来。
"""
import argparse
import http.server
import os
import socketserver
import sys
import urllib.parse

import sitepath  # noqa: F401

import data
import larksso
import pages
import render
import sandbox
import session
import store
import ttyproxy

BASE_PATH = sandbox.TTYD_BASE_PATH        # 与容器侧同一个常量，不各写一份
STATE_COOKIE = "mc_oauth_state"

CSS = """
:root{--fg:#1a1a1a;--mut:#6b6b6b;--line:#e2e2e2;--bg:#fbfbfa;--acc:#1f6feb;
--ok:#1a7f37;--warn:#9a6700;--err:#b42318}
*{box-sizing:border-box}
body{margin:0;font:15px/1.7 -apple-system,"PingFang SC","Helvetica Neue",sans-serif;
color:var(--fg);background:var(--bg)}
header{display:flex;align-items:center;gap:18px;padding:10px 22px;background:#fff;
border-bottom:1px solid var(--line);flex-wrap:wrap}
.brand{font-weight:700;text-decoration:none;color:var(--fg)}
nav{display:flex;gap:14px;flex:1}
nav a{text-decoration:none;color:var(--mut);padding:2px 0;border-bottom:2px solid transparent}
nav a:hover{color:var(--fg)} nav a.on{color:var(--fg);border-color:var(--acc)}
.who{color:var(--mut);font-size:13px}.who .out{margin-left:10px;color:var(--acc)}
main{max-width:880px;margin:0 auto;padding:26px 22px 60px}
h1{font-size:24px;margin:0 0 18px}h2{font-size:18px;margin:26px 0 10px}
footer{max-width:880px;margin:0 auto;padding:0 22px 40px;color:var(--mut);font-size:13px}
code{background:#f0f0ee;padding:1px 5px;border-radius:3px;font-size:.9em}
pre{background:#f6f6f4;border:1px solid var(--line);border-radius:6px;padding:10px;
overflow-x:auto;font-size:12px;margin:6px 0}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#f4f4f2}
blockquote{margin:10px 0;padding:6px 14px;border-left:3px solid var(--line);color:var(--mut)}
.muted{color:var(--mut)}
.notice{border:1px solid var(--line);border-left-width:4px;border-radius:6px;
padding:2px 14px;margin:14px 0;background:#fff}
.notice.ok{border-left-color:var(--ok)}.notice.warn{border-left-color:var(--warn)}
.notice.err{border-left-color:var(--err)}.notice.info{border-left-color:var(--acc)}
.btn{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;
padding:9px 18px;border-radius:6px;border:0;font-size:15px;cursor:pointer}
.devlogin{border:1px dashed var(--warn);border-radius:6px;padding:2px 14px 14px;margin-top:22px}
.devlogin input{padding:7px;border:1px solid var(--line);border-radius:4px;width:220px}
.devlogin button{padding:8px 14px;margin-left:6px;border:0;border-radius:4px;
background:var(--fg);color:#fff;cursor:pointer}
.term{width:100%;height:70vh;border:1px solid var(--line);border-radius:8px;background:#000}
.hint{color:var(--mut);font-size:13px}
/* 雷达图 */
.radarwrap{display:flex;gap:20px;align-items:center;flex-wrap:wrap;
background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px}
.radar{flex:0 0 auto}
.ring{fill:none;stroke:#e6e6e3;stroke-width:1}
.ring.beyond{stroke:#f0f0ee;stroke-dasharray:2 4}
.ringlabel{font-size:9px;fill:#b5b5b0}.ringlabel.beyond{fill:#d8d8d4}
.axis{stroke:#d8d8d4;stroke-width:1}
.axis.missing{stroke:#c9a227;stroke-dasharray:4 4}
.edge{stroke:var(--acc);stroke-width:2}
.vtx{fill:var(--acc)}
.gap{fill:none;stroke:#c9a227;stroke-width:2}
.dimlabel{font-size:12px;fill:var(--fg)}
.dimlevel{font-size:12px;fill:var(--acc);font-weight:700}
.dimlevel.missing{fill:#c9a227}
.legend{list-style:none;margin:0;padding:0;font-size:13px;flex:1;min-width:230px}
.legend li{margin:8px 0;display:flex;gap:8px;align-items:flex-start}
.legend .k{flex:0 0 12px;height:12px;margin-top:5px;border-radius:2px}
.legend .k.vtx{background:var(--acc);border-radius:50%}
.legend .k.gap{border:2px solid #c9a227}
.legend .k.beyond{border:1px dashed #d8d8d4}
td.lv{font-weight:700;color:var(--acc)}td.lv.missing{color:#c9a227}
.edges{margin:6px 0 0;padding-left:18px;font-size:13px;color:var(--mut)}
/* 轨道 */
.mod{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 14px;margin:8px 0}
.mod.done{border-left:4px solid var(--ok)}
.mod summary{cursor:pointer}
.state{display:inline-block;min-width:74px;font-size:12px;color:var(--mut)}
.tag{font-size:11px;background:#f0f0ee;color:var(--mut);padding:1px 6px;border-radius:9px}
.exempt{font-size:14px}.slices{font-size:13px;color:var(--mut)}
/* 证据 */
.item{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 14px;margin:6px 0}
.item summary{cursor:pointer}
.verdict{display:inline-block;min-width:44px;font-size:12px;font-weight:700}
.v-pass .verdict{color:var(--ok)}.v-fail .verdict{color:var(--err)}
.v-na .verdict,.item .verdict{color:var(--mut)}
.v-pass{border-left:4px solid var(--ok)}.v-fail{border-left:4px solid var(--err)}
.ev{list-style:none;padding:0}.ev li{margin:10px 0}
.seq{color:var(--mut);font-size:12px;margin-right:6px}
.uuid{color:var(--mut);font-size:11px;margin-left:6px}
.debrief{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 14px;margin:18px 0}
"""


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "microclass-web"
    dev_login = False

    # ---- 基础设施 ----
    def log_message(self, fmt, *a):
        # 只记方法、路径、状态 —— 不记 cookie、不记 query（query 里有 OAuth code）
        sys.stderr.write(f"{self.address_string()} {self.command} "
                         f"{self.path.split('?')[0]} {a[1] if len(a) > 1 else ''}\n")

    @property
    def secure(self):
        return self.headers.get("X-Forwarded-Proto", "").lower() == "https"

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        # 页面里没有外链资源，CSP 可以收到最紧；frame-src 只留自己（终端 iframe）
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; frame-src 'self'; form-action 'self'")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _redirect(self, to, extra=()):
        self._send(302, b"", "text/plain", (("Location", to),) + tuple(extra))

    def _cookies(self):
        return self.headers.get("Cookie", "")

    def _student(self):
        """当前会话对应的学员档案。没登录或档案没了都返回 None。"""
        sid = session.verify(session.read_cookie(self._cookies()))
        if not sid or not store.exists(sid):
            return None
        return store.load(sid)

    def _form(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    # ---- 路由 ----
    def do_GET(self):
        self._route()

    def do_POST(self):
        self._route()

    def do_HEAD(self):
        self._route()

    def _route(self):
        path, _, query = self.path.partition("?")
        q = urllib.parse.parse_qs(query)

        if path == "/static/style.css":
            return self._send(200, CSS, "text/css; charset=utf-8",
                              (("Cache-Control", "max-age=300"),))

        # 终端反代：路径前缀与容器里的 ttyd base-path 一致，逐字节转发
        if path == BASE_PATH or path.startswith(BASE_PATH + "/"):
            return self._terminal()

        if path == "/login":
            if self._student():
                return self._redirect("/track")
            return self._send(200, pages.login(dev_login=self.dev_login,
                                               error=(q.get("e") or [""])[0],
                                               open_id=(q.get("oid") or [""])[0]))
        if path == "/auth/lark/start":
            return self._lark_start()
        if path == "/auth/lark/callback":
            return self._lark_callback(q)
        if path == "/auth/dev" and self.command == "POST":
            return self._dev_login()
        if path == "/logout":
            return self._redirect("/login", (("Set-Cookie", session.clear_header(self.secure)),))

        rec = self._student()
        if not rec:
            return self._redirect("/login")

        if path == "/":
            return self._redirect("/track")
        if path == "/assess":
            return self._send(200, pages.assess(rec, base_path=BASE_PATH))
        if path == "/assess/start" and self.command == "POST":
            return self._start_sandbox(rec)
        if path == "/track":
            return self._send(200, pages.track(rec))
        if path == "/me":
            return self._send(200, pages.me(rec))
        if path == "/evidence":
            return self._send(200, pages.evidence(rec))
        if path.startswith("/evidence/cast/"):
            return self._cast(rec, path[len("/evidence/cast/"):])

        return self._send(404, render.page("找不到这一页", "<p>路径不对。</p>",
                                           student=rec["student"]))

    # ---- 登录 ----
    def _lark_start(self):
        if not larksso.configured():
            return self._redirect("/login?e=" + urllib.parse.quote(
                "没有配置飞书应用（MICROCLASS_LARK_APP_ID / _APP_SECRET）"))
        state = larksso.new_state()
        # state 同时进 URL 和 cookie，回调时两边必须对上 —— 防 CSRF。
        c = f"{STATE_COOKIE}={state}; Path=/auth; Max-Age=600; HttpOnly; SameSite=Lax" \
            + ("; Secure" if self.secure else "")
        return self._redirect(larksso.authorize_url(self._redirect_uri(), state),
                              (("Set-Cookie", c),))

    def _redirect_uri(self):
        base = os.environ.get("MICROCLASS_WEB_BASE")
        if not base:
            host = self.headers.get("Host", "127.0.0.1")
            base = f"{'https' if self.secure else 'http'}://{host}"
        return base.rstrip("/") + "/auth/lark/callback"

    def _lark_callback(self, q):
        got_state = (q.get("state") or [""])[0]
        cookie_state = ""
        for chunk in self._cookies().split(";"):
            k, _, v = chunk.strip().partition("=")
            if k == STATE_COOKIE:
                cookie_state = v
        if not got_state or got_state != cookie_state:
            return self._redirect("/login?e=" + urllib.parse.quote(
                "state 对不上，可能是过期或跨站请求。重新登录一次。"))
        code = (q.get("code") or [""])[0]
        if not code:
            return self._redirect("/login?e=" + urllib.parse.quote("飞书没有回传授权码"))
        try:
            oid = larksso.open_id(larksso.exchange(code, self._redirect_uri()))
        except larksso.SSOError as e:
            return self._redirect("/login?e=" + urllib.parse.quote(str(e)))
        rec = data.student_by_lark(oid)
        if not rec:
            # 登录成功但没档案：把 open_id 显示出来让人去找管理员开通。
            # **不自动建档案、不自动建容器** —— 见 data.student_by_lark 的注释。
            return self._redirect("/login?oid=" + urllib.parse.quote(oid))
        return self._enter(rec["student"])

    def _dev_login(self):
        if not self.dev_login:
            return self._send(403, render.page("不可用", "<p>开发登录没有启用。</p>"))
        sid = (self._form().get("student") or "").strip()
        if not _ok_id(sid) or not store.exists(sid):
            return self._redirect("/login?e=" + urllib.parse.quote(f"没有学员 {sid}"))
        return self._enter(sid)

    def _enter(self, student):
        return self._redirect("/track", (
            ("Set-Cookie", session.cookie_header(session.issue(student), secure=self.secure)),
            ("Set-Cookie", f"{STATE_COOKIE}=; Path=/auth; Max-Age=0"),
        ))

    # ---- 沙盒 ----
    def _start_sandbox(self, rec):
        if data.graduated(rec):
            return self._send(403, render.page(
                "已毕业", render.notice("毕业之后不再提供沙盒。", "info"),
                student=rec["student"]))
        try:
            sandbox.start(rec["student"])
        except Exception as e:                      # noqa: BLE001 docker 什么都可能抛
            return self._send(500, render.page(
                "启动失败", render.notice(f"起容器失败：`{e}`\n\n请管理员看一眼宿主机。", "err"),
                student=rec["student"], active="/assess"))
        return self._redirect("/assess")

    def _terminal(self):
        rec = self._student()
        if not rec:
            return self._send(401, "请先登录", "text/plain; charset=utf-8")
        if data.graduated(rec):
            return self._send(403, "已毕业，终端已停用", "text/plain; charset=utf-8")
        if sandbox.container_state(rec["student"]) != "running":
            return self._send(409, "沙盒没在运行", "text/plain; charset=utf-8")
        try:
            ttyproxy.tunnel(self, port=rec["ttyd_port"],
                            user=rec["ttyd_user"], password=rec["ttyd_password"])
        except ttyproxy.ProxyError as e:
            self._send(502, str(e), "text/plain; charset=utf-8")

    def _cast(self, rec, name):
        # 先解码：不解码的话合法文件名里的百分号编码取不出文件。
        # 下面这道分隔符检查是**第二层**，不是唯一一层 —— 变异测试里把它整条删掉，
        # 测试仍然全绿，因为真正拦住越权的是再下面那个白名单。留着它是纵深防御，
        # 但别以为有测试在盯着它。
        name = urllib.parse.unquote(name)
        if "/" in name or "\\" in name or not name.endswith(".cast"):
            return self._send(400, "文件名不合法", "text/plain; charset=utf-8")
        # 白名单才是真正的闸：只在**这名学员自己的**证据目录里逐个比对文件名。
        # 上面那道检查是第二层，不是唯一一层。
        for c in data.cast_files(rec["student"]):
            if c.name == name:
                return self._send(200, c.read_bytes(), "application/x-asciicast",
                                  (("Content-Disposition",
                                    f'attachment; filename="{name}"'),))
        return self._send(404, "没有这个录屏", "text/plain; charset=utf-8")


def _ok_id(sid):
    try:
        store.check_id(sid)
        return True
    except store.StoreError:
        return False


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv=None):
    ap = argparse.ArgumentParser(description="AI 微课堂 web 前端")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7900)
    ap.add_argument("--dev-login", action="store_true",
                    help="启用「填学员 ID 直接进」的开发入口（仅限监听回环）")
    a = ap.parse_args(argv)

    if a.dev_login:
        # 这个入口等于没有认证。三道闸，缺一不可：
        # 必须显式打开、必须只监听回环、必须没配飞书 —— 配了飞书说明是正式环境。
        if a.host not in ("127.0.0.1", "localhost", "::1"):
            raise SystemExit("错误：--dev-login 只允许配合 --host 127.0.0.1 使用")
        if larksso.configured():
            raise SystemExit("错误：已经配了飞书应用，不能再开 --dev-login")
        print("！！ 开发登录已启用：任何能连到这个端口的人都能扮演任意学员。", file=sys.stderr)
    elif not larksso.configured():
        raise SystemExit(
            "错误：没有配置飞书应用，登录不可用。\n"
            "  正式环境：设 MICROCLASS_LARK_APP_ID / MICROCLASS_LARK_APP_SECRET\n"
            "  本地开发：加 --dev-login（只允许 --host 127.0.0.1）")

    Handler.dev_login = a.dev_login
    srv = Server((a.host, a.port), Handler)
    print(f"microclass-web 起来了：http://{a.host}:{a.port}/  "
          f"（终端反代挂在 {BASE_PATH}）", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
