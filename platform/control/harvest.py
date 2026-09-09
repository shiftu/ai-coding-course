#!/usr/bin/env python3
"""把一名学员的证据链取出来，交给批改 agent。

四类证据（设计文档 §4.3），全部是**本来就落在那里**的东西 ——
不建实时信号流水线，测评结束后一次性读取：

  ① claude-code 会话记录   /workspace/.claude/projects/**/*.jsonl
  ② git 仓库状态           /workspace 下每个仓库的 log/status/diff
  ③ asciinema 录屏         /evidence/*.cast（已经在宿主机上）
  ④ 网关请求日志           按这名学员的 api_key_id 过滤

    python3 harvest.py <学员> [--out 目录]

毕业之后拒绝执行 —— §8 的硬边界不能只写在文档里。
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gateway
import sandbox
import store

# 会话记录可能很大，但它是最核心的证据源，不设上限；
# git diff 反过来 —— 学员可能 commit 了一个巨大的依赖目录
MAX_DIFF_BYTES = 2_000_000


class HarvestError(RuntimeError):
    pass


# 学员会话里可能还活着的 agent 进程。采证撞上它们就会拿到半截状态。
LIVE_AGENT_RE = r"(claude|codex|hermes)"


def live_agents(student):
    """容器里还有没有在跑的 agent 进程。

    **为什么必须查**：`claude -p` 返回之后，它的工具调用不一定落完盘；
    学员从 ttyd 断开也不代表 agent 停了。实测踩过一次 ——
    同一名学员先后两次采证，第一次 git 0 处改动（判"交白卷"），
    两分钟后第二次 13 行 diff（判 L2）。**同一份作业两个结论**。

    采证是给判定用的，判定要可复现，所以采证必须在静止态做。
    """
    if sandbox.container_state(student) != "running":
        return []          # 容器都停了，肯定静止
    rc, out = sandbox.exec_in(
        student, f"ps -eo pid,etime,args 2>/dev/null | grep -E '{LIVE_AGENT_RE}' "
                 "| grep -v grep | grep -v 'ps -eo'", login=False)
    return [l.strip() for l in out.splitlines() if l.strip()]


def _in_volume(student, script):
    """在学员的卷上跑一段 shell。容器停着也能读 —— 挂个一次性容器就行。"""
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{sandbox.volume_name(student)}:/workspace",
         "--entrypoint", "/bin/bash", sandbox.IMAGE, "-c", script],
        capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def _copy_out(student, container_glob, dest):
    """把卷里的文件拷到宿主机。用 tar 走 stdout，不依赖容器在跑。"""
    os.makedirs(dest, exist_ok=True)
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{sandbox.volume_name(student)}:/workspace",
         "--entrypoint", "/bin/bash", sandbox.IMAGE, "-c",
         f"cd /workspace && tar cf - {container_glob} 2>/dev/null || true"],
        capture_output=True)
    if not r.stdout:
        return 0
    t = subprocess.run(["tar", "xf", "-", "-C", dest], input=r.stdout, capture_output=True)
    if t.returncode != 0:
        raise HarvestError(f"解包失败：{t.stderr.decode()[:200]}")
    n = 0
    for _, _, files in os.walk(dest):
        n += len(files)
    return n


def transcripts(student, outdir):
    dest = os.path.join(outdir, "transcripts")
    n = _copy_out(student, ".claude/projects", dest)
    return {"files": n, "path": dest}


def git_state(student, outdir):
    """每个仓库存三份：log / status / diff。

    存 status 而不只是 diff：学员可能改完就 commit 了，那时 diff 是空的，
    只看 diff 会得出「什么都没改」的结论 —— 又一个空集陷阱。
    """
    dest = os.path.join(outdir, "git")
    os.makedirs(dest, exist_ok=True)
    rc, repos, _ = _in_volume(student, "find /workspace -maxdepth 3 -name .git -type d 2>/dev/null")
    found = []
    for gitdir in repos.split():
        repo = os.path.dirname(gitdir)
        name = os.path.basename(repo) or "workspace"
        parts = {}
        for label, cmd in (
            ("log", "git log --oneline -50 2>&1"),
            ("status", "git status --porcelain=v1 2>&1"),
            ("diff", "git diff 2>&1"),
            ("diff-staged", "git diff --staged 2>&1"),
            ("branch", "git branch --show-current 2>&1"),
        ):
            _, out, _ = _in_volume(student, f"cd {repo} && {cmd}")
            if label.startswith("diff") and len(out) > MAX_DIFF_BYTES:
                out = out[:MAX_DIFF_BYTES] + f"\n…（截断，原始 {len(out)} 字节）\n"
            parts[label] = out
        path = os.path.join(dest, f"{name}.json")
        with open(path, "w") as f:
            json.dump({"repo": repo, **parts}, f, ensure_ascii=False, indent=2)
        found.append({"repo": repo, "file": path,
                      "commits": len([l for l in parts["log"].splitlines() if l.strip()]),
                      "dirty": len([l for l in parts["status"].splitlines() if l.strip()])})
    return {"repos": found, "path": dest}


def casts(student, outdir):
    """录屏本来就 bind mount 在宿主机上，这里只做清点，不搬家。"""
    ev = store.evidence_dir(student)
    files = sorted(f for f in os.listdir(ev) if f.endswith(".cast"))
    items = []
    for f in files:
        p = os.path.join(ev, f)
        try:
            head = json.loads(open(p).readline())
        except Exception:
            head = {}
        items.append({
            "file": p, "bytes": os.path.getsize(p),
            "version": head.get("version"),
            "size": f"{head.get('width')}x{head.get('height')}",
            "replayable": bool(head.get("version") == 2 and head.get("width")),
        })
    return {"casts": items, "path": ev}


def gateway_logs(student, rec, outdir, limit=200):
    rows = gateway.request_logs(rec["gateway_key_id"], limit=limit)
    path = os.path.join(outdir, "gateway-logs.json")
    with open(path, "w") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return {"rows": len(rows), "key_id": rec["gateway_key_id"], "path": path,
            "hit_limit": len(rows) >= limit}


def has_graded_harvest(student):
    """这名学员是不是已经有过至少一批批改结果。

    `sandctl grade-all` 靠它判断要不要跳过 —— 已批改的人不重新采证、
    不重新判定，旧的 harvest-*/grade/grade.json 永远不会被批量命令碰。
    只判"有没有"，不关心是哪一批、判得好不好 —— 那是重判的活，
    重判是显式的单条操作，不混进批量命令里。
    """
    d = store.evidence_dir(student)
    if not os.path.isdir(d):
        return False
    return any(
        os.path.isfile(os.path.join(d, name, "grade", "grade.json"))
        for name in os.listdir(d) if name.startswith("harvest-")
    )


def harvest(student, out=None, *, allow_live=False, stop_first=False):
    rec = store.load(student)
    if not rec.get("collecting"):
        raise HarvestError(
            f"{student} 已于 {rec.get('graduated_at')} 毕业 —— §8 硬边界：毕业后零采集，拒绝执行。\n"
            f"课程期内已采集的证据仍在 {rec.get('evidence_dir')}，那是学员本人的证据页素材。")

    # 静止态检查（见 live_agents 的说明）。默认宁可不采，也不采半截。
    if stop_first:
        sandbox.stop(student)
    live = live_agents(student)
    if live and not allow_live:
        raise HarvestError(
            f"{student} 的容器里还有 agent 在跑，现在采证会拿到半截状态：\n  "
            + "\n  ".join(live[:5])
            + "\n加 --stop-first 先停容器（推荐），或 --allow-live 明确接受半截证据。")

    outdir = out or os.path.join(store.evidence_dir(student), f"harvest-{store.now().replace(':', '')}")
    os.makedirs(outdir, exist_ok=True)

    manifest = {
        "student": student, "harvested_at": store.now(),
        "mode": rec.get("mode"), "track": rec.get("track"),
        # 环境身份三件套一起进 manifest。只抄 image 那个 tag 是不够的 ——
        # tag 会被后来的构建挪走，而这份 manifest 是要跟着成绩存档的：
        # 半年后有人问"当时判他的是哪套环境"，能答上来的是 image_id。
        "image": rec.get("image"), "image_id": rec.get("image_id"),
        "image_stamp": rec.get("image_stamp"),
        "quiescent": not live,          # 采证时是不是静止态
        "live_agents_at_harvest": live, # 非空 = 这份证据可能不完整
        "sources": {
            "transcript": transcripts(student, outdir),
            "git": git_state(student, outdir),
            "cast": casts(student, outdir),
            "gateway": gateway_logs(student, rec, outdir),
        },
    }
    # 明确记下哪几路是空的 —— 空证据必须是显式结论，不能让下游默默当成"没问题"
    manifest["empty_sources"] = [
        name for name, ok in (
            ("transcript", manifest["sources"]["transcript"]["files"] > 0),
            ("git", bool(manifest["sources"]["git"]["repos"])),
            ("cast", bool(manifest["sources"]["cast"]["casts"])),
            ("gateway", manifest["sources"]["gateway"]["rows"] > 0),
        ) if not ok
    ]
    path = os.path.join(outdir, "manifest.json")
    with open(path, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return outdir, manifest


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("student")
    p.add_argument("--out", default=None)
    p.add_argument("--stop-first", action="store_true",
                   help="先停容器再采证——保证静止态，推荐用于测评")
    p.add_argument("--allow-live", action="store_true",
                   help="明确接受可能不完整的证据（会记进 manifest）")
    a = p.parse_args()
    try:
        outdir, m = harvest(a.student, a.out,
                            allow_live=a.allow_live, stop_first=a.stop_first)
    except (HarvestError, store.StoreError, gateway.GatewayError) as e:
        print(f"错误：{e}", file=sys.stderr)
        raise SystemExit(1)
    s = m["sources"]
    print(f"{a.student} 的证据已取到 {outdir}")
    print(f"  ① 会话记录  {s['transcript']['files']} 个文件")
    print(f"  ② git 仓库  {len(s['git']['repos'])} 个"
          + "".join(f"\n       {r['repo']}：{r['commits']} 个提交，{r['dirty']} 处未提交改动"
                    for r in s["git"]["repos"]))
    print(f"  ③ 录屏      {len(s['cast']['casts'])} 段"
          + "".join(f"\n       {os.path.basename(c['file'])} {c['size']} "
                    f"{'可回放' if c['replayable'] else '⚠ 不可回放'}"
                    for c in s["cast"]["casts"]))
    print(f"  ④ 网关日志  {s['gateway']['rows']} 条"
          + ("（已达上限，可能还有更多）" if s["gateway"]["hit_limit"] else ""))
    if not m["quiescent"]:
        print("\n  ⚠ 采证时容器里还有 agent 在跑，这份证据可能不完整 —— 不要据此定级")
    if m["empty_sources"]:
        print(f"\n  ⚠ 这几路是空的：{'、'.join(m['empty_sources'])}"
              "\n    空证据不等于学员没做 —— 先查采集本身有没有坏，再下判断")


if __name__ == "__main__":
    main()
