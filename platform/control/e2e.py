#!/usr/bin/env python3
"""sandctl 端到端验收：开号 → 用 → 毕业 → 销号，每步都验真。

跑法（要花一点网关的钱，最后一项是真的调模型）：
    python3 e2e.py

用真 pty 驱动，因为「测评模式自动录屏」的分支要求 [ -t 0 ] ——
用 docker exec 不带 tty 是测不到这条路径的。
"""
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
import fcntl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gateway
import sandbox
import store

# 毕业前后那两条对照请求用的模型：和沙盒里的统一模型一致，都从 versions.lock 来，
# 别在这里另写一个只在某个网关上存在的别名。
PROBE_MODEL = sandbox.locked("MODEL")
assert PROBE_MODEL, "versions.lock 里没有 MODEL"

STU = "e2e-stu"
COLS, ROWS = 120, 32
results = []


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"\n       {detail}" if detail and not ok else ""))


def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def sandctl(*args, expect_ok=True):
    rc, out = sh(f"./sandctl {' '.join(args)}")
    if expect_ok and rc != 0:
        print(out)
        raise SystemExit(f"sandctl {' '.join(args)} 失败")
    return out


def drive_pty(commands, settle=6.0):
    """开一个真 pty 连进学员容器，敲几条命令，返回屏幕输出。"""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("docker", ["docker", "exec", "-it", sandbox.container_name(STU), "/bin/bash", "-l"])
        os._exit(1)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))

    buf = b""

    def pump(seconds):
        nonlocal buf
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.3)
            if r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    return
                if not chunk:
                    return
                buf += chunk

    pump(3.0)                      # 等录制层和 shell 都就绪再敲，否则输入会掉
    for c in commands:
        os.write(fd, c.encode() + b"\n")
        pump(settle)
    os.write(fd, b"exit\n")
    pump(3.0)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return buf.decode(errors="replace")


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print("== 0. 清场 ==")
    sh(f"./sandctl destroy {STU}")
    sh(f"rm -rf {os.path.join(store.EVIDENCE_DIR, STU)}")

    print("\n== 1. 开号 ==")
    out = sandctl("create", STU, "--mode", "assessment", "--track", "A")
    step("create 通过且自检全绿", "自检通过" in out, out[-300:])
    rec = store.load(STU)
    port, pw = rec["ttyd_port"], rec["ttyd_password"]

    print("\n== 2. ttyd 鉴权 ==")
    for label, auth, want in (("无凭证", "", "401"), ("错口令", f"-u {STU}:wrong", "401"),
                              ("对口令", f"-u {STU}:{pw}", "200")):
        _, code = sh(f"curl -s -o /dev/null -w '%{{http_code}}' -m 5 {auth} "
                     f"http://127.0.0.1:{port}{sandbox.TTYD_BASE_PATH}/")
        step(f"{label} → {want}", code == want, f"实际 {code}")
    # ttyd 挂在 base-path 下是 web 反代的前提（ttyd 页面引用绝对路径 /ws、/token，
    # 挂在根上就没法反代）。根路径必须是 404 —— 这条一旦变了，前端要跟着改。
    _, code = sh(f"curl -s -o /dev/null -w '%{{http_code}}' -m 5 -u {STU}:{pw} "
                 f"http://127.0.0.1:{port}/")
    step(f"根路径不提供服务（ttyd 在 {sandbox.TTYD_BASE_PATH} 下）", code == "404", f"实际 {code}")
    _, ports = sh(f"docker port {sandbox.container_name(STU)}")
    step("只绑回环，没暴露到 0.0.0.0", "127.0.0.1:" in ports and "0.0.0.0" not in ports, ports)

    print("\n== 3. 真 pty 会话（测评模式，应自动录屏）==")
    screen = drive_pty([
        "echo MARK-$MICROCLASS_MODE-$MICROCLASS_TRACK",
        "python3 -m pytest --version",
        'claude -p "Use the Bash tool to run: python3 -c \\"print(6*7)\\" then say the number." --output-format json > /workspace/claude-out.json 2>&1; echo CLAUDE-DONE',
    ], settle=8.0)
    step("环境变量在会话里可见", "MARK-assessment-A" in screen, screen[-400:])
    step("pytest 在登录 shell 里跑得动", "pytest 8.3.4" in screen, screen[-400:])
    step("claude 跑完了", "CLAUDE-DONE" in screen, screen[-400:])

    print("\n== 4. 证据链四件套 ==")
    ev = store.evidence_dir(STU)
    casts = [f for f in os.listdir(ev) if f.endswith(".cast")]
    step("① 录屏产出 .cast", bool(casts), f"{ev} 里是 {os.listdir(ev)}")
    if casts:
        head = json.loads(open(os.path.join(ev, casts[0])).readline())
        step("  cast 是 v2", head.get("version") == 2, str(head))
        step("  cast 尺寸不是 0（0 的话回放一片空白）",
             head.get("width", 0) > 0 and head.get("height", 0) > 0, str(head))
        body = open(os.path.join(ev, casts[0])).read()
        step("  cast 里录到了学员敲的命令", "MARK-assessment-A" in body, "cast 里找不到 MARK")

    rc, out = sandbox.exec_in(STU, 'ls -d $CLAUDE_CONFIG_DIR/projects/*/ 2>/dev/null | head -1')
    step("② claude transcript 落在持久卷上", rc == 0 and "/workspace/.claude/projects/" in out, out)

    rc, out = sandbox.exec_in(STU, 'cd /workspace && git init -q t && cd t && git status --porcelain; echo GIT-OK')
    step("③ git 可用（仓库状态是证据源之一）", "GIT-OK" in out, out)

    logs = gateway.request_logs(rec["gateway_key_id"], limit=20)
    step("④ 网关日志按这把 key 归到这名学员", len(logs) > 0, f"这把 key 一条日志都没有")

    rc, out = sandbox.exec_in(STU, 'python3 -c "import json;d=json.load(open(\'/workspace/claude-out.json\'));print(len(d[\'permission_denials\']), d[\'result\'][:40])"')
    step("claude 0 次权限拦截（证据链没被毒化）", out.strip().startswith("0 "), out)

    print("\n== 5. 毕业 = §8 隐私开关 ==")
    # 必须在 graduate 之前把明文 key 抓在手里 —— 否则「吊销后还能不能用」
    # 这条反向验证会拿空 key 去问，那是在验「空 key 被拒」，是道假题。
    live_key = store.get_key(STU)
    assert live_key, "毕业前应当有明文 key，拿不到就没法做反向验证"
    _, before = sh(f"curl -s -o /dev/null -w '%{{http_code}}' -m 15 -X POST "
                   f"{gateway.DEFAULT_BASE}/v1/messages -H 'content-type: application/json' "
                   f"-H 'anthropic-version: 2023-06-01' -H 'x-api-key: {live_key}' "
                   f"-d '{{\"model\":\"{PROBE_MODEL}\",\"max_tokens\":8,"
                   f"\"messages\":[{{\"role\":\"user\",\"content\":\"hi\"}}]}}'")
    step("毕业前：这把 key 能用（对照组）", before == "200", f"HTTP {before}")

    out = sandctl("graduate", STU)
    step("graduate 跑通", "已毕业" in out and "revoked_at=" in out, out)
    step("网关账面上 key 已置 revoked_at", not gateway.key_active(rec["gateway_key_id"]),
         str(gateway.key_record(rec["gateway_key_id"])))
    step("本地明文 key 已删", store.get_key(STU) is None)
    step("状态标记为停止采集", store.load(STU)["collecting"] is False)

    # 反向验证：同一把 key、同一条请求，毕业后必须被拒。
    # 前后对照才叫证明 —— 只看毕业后被拒，说明不了是吊销起的作用。
    #
    # 这里**必须静默等待，不能轮询**。网关鉴权命中缓存时不查 DB（看不到
    # revoked_at），而且每次鉴权成功都会把 expiresAt 再推后 60 秒。
    # 每 10 秒探一次的话，探测请求自己就在给缓存续命，永远等不到 401 ——
    # 第一版就是这么写的，结果等满 89 秒仍然 200，红的是测试不是产品。
    quiet = gateway.AUTH_CACHE_TTL + 15
    print(f"     （静默等待 {quiet}s 让网关鉴权缓存自然过期；期间一个请求都不发）")
    time.sleep(quiet)
    _, after = sh(f"curl -s -o /dev/null -w '%{{http_code}}' -m 15 -X POST "
                  f"{gateway.DEFAULT_BASE}/v1/messages -H 'content-type: application/json' "
                  f"-H 'anthropic-version: 2023-06-01' -H 'x-api-key: {live_key}' "
                  f"-d '{{\"model\":\"{PROBE_MODEL}\",\"max_tokens\":1,"
                  f"\"messages\":[{{\"role\":\"user\",\"content\":\"hi\"}}]}}'")
    step(f"毕业后静默 {quiet}s：同一把 key 同一条请求被拒（{before} → {after}）",
         after != "200", f"仍然 HTTP 200 —— 采集没停")

    print("\n== 6. 销号 ==")
    out = sandctl("destroy", STU)
    step("容器和卷都没了", sandbox.container_state(STU) == "absent", out)
    step("档案没了", not store.exists(STU))
    step("证据目录被保留（要删得人工确认）", os.path.isdir(ev))

    ok = sum(1 for _, o, _ in results if o)
    bad = len(results) - ok
    print("\n───────────────────────────")
    print(f"通过 {ok}，失败 {bad}")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
