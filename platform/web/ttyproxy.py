#!/usr/bin/env python3
"""把学员自己的 ttyd 反代出去。

容器上的 ttyd 只监听 127.0.0.1，并且带 basic auth。浏览器**永远拿不到**那对
账号口令 —— 前端在这里替学员把 Authorization 头加上去。

实现上不解析上游响应，只做字节对拷：这样 HTTP 和 WebSocket 升级走的是同一条
路径，不需要为 101 单独写一套。ttyd 的终端本来就是一条长连接的 WebSocket。
"""
import base64
import socket
import threading

BUF = 65536
CONNECT_TIMEOUT = 5

# 这些头不能原样转给 ttyd。
# Cookie 尤其重要：会话 cookie 是这个 web 前端的凭证，容器里的 ttyd
# 没有任何理由看到它。Authorization 由我们自己覆盖。
DROP = {"cookie", "authorization", "host", "connection"}
# Connection/Upgrade 属于逐跳头，但 WebSocket 升级又必须保留它们 —— 
# 所以 Connection 单独判断，不能一刀切地删。
HOP_KEEP_FOR_WS = {"upgrade"}


class ProxyError(RuntimeError):
    pass


def _raw_request(handler, port, user, password):
    lines = [f"{handler.command} {handler.path} {handler.request_version}",
             f"Host: 127.0.0.1:{port}",
             "Authorization: Basic " + base64.b64encode(
                 f"{user}:{password}".encode("utf-8")).decode("ascii")]
    for k, v in handler.headers.items():
        lk = k.lower()
        if lk in DROP:
            continue
        lines.append(f"{k}: {v}")
    conn = handler.headers.get("Connection", "")
    if "upgrade" in conn.lower() or handler.headers.get("Upgrade"):
        lines.append(f"Connection: {conn or 'Upgrade'}")
    else:
        lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8", "replace")


def _pump(src_read, dst_write, on_done):
    try:
        while True:
            chunk = src_read(BUF)
            if not chunk:
                break
            dst_write(chunk)
    except (OSError, ValueError):
        pass
    finally:
        on_done()


def tunnel(handler, *, port, user, password):
    """把当前这条连接接到 127.0.0.1:port 上，双向对拷到任意一端关闭。"""
    handler.close_connection = True
    try:
        up = socket.create_connection(("127.0.0.1", port), CONNECT_TIMEOUT)
    except OSError as e:
        raise ProxyError(f"连不上沙盒终端（127.0.0.1:{port}）：{e}") from None

    try:
        up.sendall(_raw_request(handler, port, user, password))
        body_len = int(handler.headers.get("Content-Length") or 0)
        while body_len > 0:
            chunk = handler.rfile.read(min(BUF, body_len))
            if not chunk:
                break
            up.sendall(chunk)
            body_len -= len(chunk)

        up.settimeout(None)
        handler.connection.settimeout(None)
        done = threading.Event()

        def shut():
            done.set()
            for s in (up, handler.connection):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        # read1：拿到多少转多少，不等凑满一个缓冲区 —— 终端要的是低延迟。
        t = threading.Thread(target=_pump,
                             args=(handler.rfile.read1, up.sendall, shut), daemon=True)
        t.start()
        _pump(up.recv, lambda b: (handler.wfile.write(b), handler.wfile.flush()), shut)
        done.wait(timeout=1)
    finally:
        try:
            up.close()
        except OSError:
            pass
