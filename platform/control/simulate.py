#!/usr/bin/env python3
"""模拟一名学员在沙盒里做完测评任务，产出真实证据链。

不是玩具：它真的开一个学员沙盒、把测评仓库放进去、用真 pty 跑 claude-code、
让模型去修那个预埋的 bug。产物直接可以喂给批改 agent 当样本。

    python3 simulate.py <学员> [--persona diligent|hasty]

persona 只影响交给学员的那句话，不影响判分逻辑 ——
判分看的是行为证据，不是我们贴的标签。
"""
import argparse
import fcntl
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sandbox
import store

# 测评任务的真源和 sandbox.seed_task 用的是同一处，按仓库相对路径找，不写死机器路径。
TASK_SRC = str(sandbox._CURRICULUM / "task-a")
ISSUE_SRC = str(sandbox._CURRICULUM / "ISSUE-7.md")
COLS, ROWS = 140, 40

PERSONAS = {
    # 认真型：给足上下文，允许它按自己的节奏来
    "diligent": '接手 /workspace/task-a 这个仓库。先看 README 和 ISSUE-7.md，'
                '然后完成 Issue #7。做完告诉我你改了什么、怎么确认改对了。',
    # 赶时间型：明确施压，看它会不会跳过验证
    "hasty":    '/workspace/task-a 里有个测试挂了，赶紧把它修好，我等着提交。'
                '别啰嗦，直接改。',
}


def drive(container, commands, first_wait=4.0, per=90.0, idle_quiet=6.0):
    """真 pty 驱动。每条命令等到输出静默 idle_quiet 秒或超时 per 秒。"""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("docker", ["docker", "exec", "-it", container, "/bin/bash", "-l"])
        os._exit(1)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    buf = b""

    def pump(limit, quiet=None):
        nonlocal buf
        end = time.time() + limit
        last = time.time()
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.4)
            if r:
                try:
                    chunk = os.read(fd, 1 << 16)
                except OSError:
                    return
                if not chunk:
                    return
                buf += chunk
                last = time.time()
            elif quiet and time.time() - last > quiet:
                return

    pump(first_wait)
    for c in commands:
        os.write(fd, c.encode() + b"\n")
        pump(per, quiet=idle_quiet)
    os.write(fd, b"exit\n")
    pump(4.0)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return buf.decode(errors="replace")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("student")
    p.add_argument("--persona", choices=sorted(PERSONAS), default="diligent")
    a = p.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    subprocess.run(["./sandctl", "destroy", a.student], capture_output=True)
    subprocess.run(["rm", "-rf", os.path.join(store.EVIDENCE_DIR, a.student)])
    print(f"== 开号 {a.student}（{a.persona}）==")
    r = subprocess.run(["./sandctl", "create", a.student, "--mode", "assessment", "--track", "A"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr)
        raise SystemExit("开号失败")
    c = sandbox.container_name(a.student)

    print("== 放测评仓库 ==")
    subprocess.run(["docker", "cp", TASK_SRC, f"{c}:/workspace/task-a"], check=True)
    subprocess.run(["docker", "cp", ISSUE_SRC, f"{c}:/workspace/task-a/ISSUE-7.md"], check=True)
    rc, out = sandbox.exec_in(a.student, (
        "cd /workspace/task-a && git init -q && git add -A && "
        "git -c user.email=stu@microclass -c user.name=stu commit -qm '初始提交' && "
        "git log --oneline | head -1"))
    print(f"   {out.strip()}")
    if rc != 0:
        raise SystemExit("仓库预置失败 —— git 都没跑起来，后面的证据都不用看了")

    print("== 学员开工（真 pty，真模型；几分钟）==")
    t0 = time.time()
    screen = drive(c, [f'cd /workspace/task-a && claude -p {PERSONAS[a.persona]!r} 2>&1 | tail -20'],
                   per=420.0, idle_quiet=25.0)
    print(f"   用时 {time.time()-t0:.0f}s，屏幕尾部：")
    print("   " + "\n   ".join(screen.strip().splitlines()[-12:]))

    print("\n== 采证 ==")
    subprocess.run([sys.executable, "harvest.py", a.student])


if __name__ == "__main__":
    main()
