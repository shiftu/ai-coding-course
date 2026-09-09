#!/usr/bin/env python3
"""web 前端的离线端到端测试。

真的把服务器起起来，用 HTTP 打进去 —— 不 mock 路由、不直接调页面函数。
只 mock 一样东西：`sandbox.container_state`，因为它要 docker，而这些断言
（登录闸、越权、路径穿越、未测得怎么画）和 docker 没关系。

跑法：python3 test_web.py
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

TMP = tempfile.mkdtemp(prefix="mc-web-test-")
os.environ["MICROCLASS_STATE"] = TMP          # 必须在 import store 之前
os.environ.pop("MICROCLASS_LARK_APP_ID", None)
os.environ.pop("MICROCLASS_LARK_APP_SECRET", None)
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import sitepath  # noqa: E402,F401
import sandbox   # noqa: E402
import serve     # noqa: E402
import session   # noqa: E402
import store     # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}" + (f" —— {detail}" if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


# ---- 造数据 ---------------------------------------------------------------

GRADE = {
    "student": "stu-ok", "graded_at": "2026-08-21T04:17:13Z", "session_count": 1,
    "rubric_items_missing": [],
    "results": {
        "tool/env-works": {"verdict": "pass", "evidence_seq": [0]},
        "safety/no-secret-literal": {"verdict": "fail", "evidence_seq": [22]},
        "spec/scope-control": {"verdict": "n/a", "guard": "skipped-no-llm",
                               "reason": "本次以 --no-llm 运行"},
    },
    "evidence": {
        "tool/env-works": [{"seq": 0, "tool": "Bash", "uuid": "u-0",
                            "excerpt": "{\"command\": \"ls\"}"}],
        "safety/no-secret-literal": [{"seq": 22, "tool": "Edit", "uuid": "u-22",
                                      "excerpt": "{\"new_string\": \"sk-XXXX\"}"}],
    },
    "dimensions": {
        "工具操作": {"level": "L2", "upper_bound": None, "reason": None,
                     "edges": {"L0→L1": {"state": "crossed", "items": ["tool/env-works"]}}},
        "需求表达": {"level": "未测得", "upper_bound": None,
                     "reason": "L0→L1 没有判定条目",
                     "edges": {"L0→L1": {"state": "no-item", "items": []}}},
        "质量验证": {"level": "L2", "upper_bound": None, "reason": None, "edges": {}},
        "自动化编排": {"level": "未测得", "upper_bound": None,
                       "reason": "本次测评没有这一维的判定条目", "edges": {}},
    },
    "s1": "fail", "s1_failed_items": ["safety/no-secret-literal"],
    "overall": "待补测", "unmeasured_dimensions": ["需求表达", "自动化编排"],
    "capped_by_s1": True,
    "debrief": "# 复盘\n\n正文。", "sessions": ["/x.jsonl"],
}
MANIFEST = {"student": "stu-ok", "harvested_at": "2026-08-21T04:17:11Z",
            "quiescent": True, "live_agents_at_harvest": [], "empty_sources": [],
            "sources": {"transcript": {"files": 1}}}


def seed():
    base = {"mode": "assessment", "track": "A", "collecting": True,
            "graduated_at": None, "gateway_key_id": "ak_x",
            "image": "microclass/sandbox:test", "created_at": "2026-08-20T00:00:00Z",
            "ttyd_user": "u", "ttyd_password": "p"}
    store.save({**base, "student": "stu-ok", "ttyd_port": 7801,
                "ttyd_base_path": sandbox.TTYD_BASE_PATH,
                "container": "mc-stu-ok", "volume": "v",
                "evidence_dir": store.evidence_dir("stu-ok"),
                "lark_open_id": "ou_ok",
                "modules": {"m0-env": {"state": "exempt", "at": "2026-08-20T01:00:00Z",
                                       "by": "免修考"}}})
    store.save({**base, "student": "stu-grad", "ttyd_port": 7802,
                "container": "mc-stu-grad", "volume": "v2",
                "evidence_dir": store.evidence_dir("stu-grad"),
                "collecting": False, "graduated_at": "2026-08-21T00:00:00Z",
                "lark_open_id": "ou_grad"})

    h = pathlib.Path(store.evidence_dir("stu-ok")) / "harvest-2026-08-21T041711Z"
    (h / "grade").mkdir(parents=True)
    (h / "grade" / "grade.json").write_text(json.dumps(GRADE, ensure_ascii=False), encoding="utf-8")
    (h / "grade" / "debrief.md").write_text("# 复盘\n\n埋点全部摊开。", encoding="utf-8")
    (h / "manifest.json").write_text(json.dumps(MANIFEST, ensure_ascii=False), encoding="utf-8")
    (pathlib.Path(store.evidence_dir("stu-ok")) / "session.cast").write_text(
        '{"version":2,"width":140,"height":40}\n', encoding="utf-8")


# ---- HTTP 小工具 ----------------------------------------------------------

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def req(url, *, cookie=None, data=None):
    r = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if cookie:
        r.add_header("Cookie", cookie)
    try:
        with OPENER.open(r, timeout=10) as resp:
            return resp.status, dict(resp.getheaders()), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def main():
    seed()
    # docker 不参与这组断言：stu-ok 的容器当作在跑，stu-grad 的当作停了
    sandbox.container_state = lambda s: "running" if s == "stu-ok" else "exited"

    serve.Handler.dev_login = True
    srv = serve.Server(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    try:
        print("\n== 登录闸 ==")
        for p in ("/track", "/me", "/evidence", "/assess", "/"):
            st, hd, _ = req(base + p)
            check(f"未登录 {p} → 跳登录", st == 302 and hd.get("Location") == "/login",
                  f"{st} {hd.get('Location')}")
        st, _, _ = req(base + "/t/")
        check("未登录 /t/ → 401", st == 401, str(st))

        st, _, body = req(base + "/login")
        check("登录页有飞书入口", "/auth/lark/start" in body)
        check("登录页有开发入口（本次开着）", "/auth/dev" in body)

        print("\n== 开发登录 ==")
        st, hd, _ = req(base + "/auth/dev", data=b"student=nobody")
        check("不存在的学员被拒", st == 302 and "e=" in (hd.get("Location") or ""))
        st, hd, _ = req(base + "/auth/dev", data=b"student=../../etc/passwd")
        check("非法 ID 被拒", st == 302 and "e=" in (hd.get("Location") or ""))

        st, hd, _ = req(base + "/auth/dev", data=b"student=stu-ok")
        cookie = (hd.get("Set-Cookie") or "").split(";")[0]
        check("登录成功并下发 cookie", st == 302 and cookie.startswith("mc_session="),
              f"{st} {hd.get('Set-Cookie')}")

        print("\n== 五个页面 ==")
        for p, must in (("/assess", "iframe"), ("/track", "免修通过"),
                        ("/me", "svg"), ("/evidence", "采证清单")):
            st, _, body = req(base + p, cookie=cookie)
            check(f"{p} 200 且内容对", st == 200 and must in body, f"{st}")

        print("\n== 雷达图必须把「未测得」画成断口 ==")
        _, _, me = req(base + "/me", cookie=cookie)
        check("两个未测得维度 → 两个空心断口", me.count('class="gap"') == 2, str(me.count('class="gap"')))
        check("两个测到的维度 → 两个顶点", me.count('class="vtx"') == 2)
        check("对角两维之间不连线（没有闭合多边形）", me.count('class="edge"') == 0)
        check("未测得的字样出现在图上", "未测得" in me)
        check("总等级待补测有解释", "有洞的向量不能取 min" in me)
        check("S1 未过但不压低维度等级", "能封顶，但不会把你的维度等级压低" in me)

        print("\n== 老容器不给白屏 ==")
        stale = store.load("stu-ok")
        store.update("stu-ok", ttyd_base_path="/")     # 模拟改前缀之前建的容器
        st, _, body = req(base + "/assess", cookie=cookie)
        check("base-path 对不上 → 说清楚要重建，而不是给 iframe",
              st == 200 and "iframe" not in body and "只会 404" in body, str(st))
        store.update("stu-ok", ttyd_base_path=stale.get("ttyd_base_path"))

        print("\n== 会话完整性 ==")
        bad = cookie[:-1] + ("a" if cookie[-1] != "a" else "b")
        st, hd, _ = req(base + "/track", cookie=bad)
        check("改一个字符的 cookie 失效", st == 302 and hd.get("Location") == "/login")
        forged = "mc_session=" + "stu-grad|9999999999|" + "0" * 64
        st, hd, _ = req(base + "/track", cookie=forged)
        check("自己编的签名无效", st == 302 and hd.get("Location") == "/login")

        print("\n== 越权与路径穿越 ==")
        st, _, _ = req(base + "/evidence/cast/session.cast", cookie=cookie)
        check("能下自己的录屏", st == 200, str(st))
        for evil in ("..%2f..%2fetc%2fpasswd", "a.txt", "%2e%2e%2fsession.cast"):
            st, _, _ = req(base + "/evidence/cast/" + evil, cookie=cookie)
            check(f"拒绝 {evil}", st in (400, 404), str(st))

        # 跨学员：stu-grad 没有录屏，session.cast 只在 stu-ok 目录里 —— 必须 404。
        # 这一条盯的是白名单本身，不是上面那道文件名检查。
        gcookie = "mc_session=" + session.issue("stu-grad")
        st, _, _ = req(base + "/evidence/cast/session.cast", cookie=gcookie)
        check("拿不到别人的录屏", st == 404, str(st))
        st, _, body = req(base + "/assess", cookie=gcookie)
        check("毕业生看不到终端", st == 200 and "iframe" not in body and "毕业即零采集" in body)
        st, _, _ = req(base + "/t/", cookie=gcookie)
        check("毕业生的终端反代 403", st == 403, str(st))
        st, _, _ = req(base + "/assess/start", cookie=gcookie, data=b"")
        check("毕业生不能重启沙盒", st == 403, str(st))
        st, _, body = req(base + "/evidence", cookie=gcookie)
        check("毕业生仍能看自己已采到的证据", st == 200 and "采集已经停止" in body)

        print("\n== 开发入口可以真的关掉 ==")
        serve.Handler.dev_login = False
        st, _, body = req(base + "/login")
        check("关掉后登录页不再出现开发入口", "/auth/dev" not in body)
        st, _, _ = req(base + "/auth/dev", data=b"student=stu-ok")
        check("关掉后 POST /auth/dev 403", st == 403, str(st))
        serve.Handler.dev_login = True

        print("\n== XSS ==")
        st, _, body = req(base + "/login?e=" + urllib.parse.quote("<img src=x onerror=alert(1)>"))
        check("错误信息被转义", "<img src=x" not in body and "&lt;img" in body)
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(TMP, ignore_errors=True)

    print(f"\n{'全部通过' if not FAILS else str(len(FAILS)) + ' 条不符：' + '、'.join(FAILS)}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
