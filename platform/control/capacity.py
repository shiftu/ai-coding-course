"""容量：这台宿主机还能再开多少个学员沙盒。

设计文档说「64G 宿主机撑 30 并发」，那是拍脑袋的假设。这里给的是两条可复算的线：

  硬上限   = (总内存 − 预留) / MEM_LIMIT
             每个容器都有内存上限（sandbox.resource_limit_args），
             所以「就算所有人同时吃满」也不会把宿主机拖垮的人数。
  实测余量 = (总内存 − 预留 − 已用) / 活跃容器的平均占用
             按现在真实的用法还能塞几个人。乐观值，agent 都在跑时会往硬上限收。

CPU 不算：agent 大部分时间在等 LLM 响应，实测活跃容器不到 5%；
真正的瓶颈更可能是网关的并发和 token 配额，那不归这里管。
"""
import json
import re
import unicodedata

import sandbox
import store

GiB = 1024 ** 3
MiB = 1024 ** 2

# 留给宿主机自己：系统、web 前端、网关、docker daemon。
# 生产机（64G）按 4 GiB 留；开发机（几个 G 的 VM）留四分之一，否则一开就是 0 人。
HOST_RESERVE_BYTES = 4 * GiB
HOST_RESERVE_FRACTION = 4
# 空闲沙盒只有 ttyd + bash，实测约 20 MiB；有 agent 在跑时几百 MiB 起。
ACTIVE_THRESHOLD_BYTES = 128 * MiB
# 一个活跃容器都没有时，拿这个数算实测余量（claude + hermes 同时跑的实测值）。
DEFAULT_ACTIVE_BYTES = 1 * GiB

# docker 两套单位都吐：stats 用 MiB/GiB（1024），system df 用 MB/GB（1000）。
_UNIT_BYTES = {
    "b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
    "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
}
_SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)\s*$")


class CapacityError(RuntimeError):
    pass


def parse_size(text):
    """'950.4MiB' / '4.66GB' / '0B' → 字节。认不出来就报错，不猜。"""
    m = _SIZE_RE.match(text or "")
    unit = m.group(2).lower() if m else None
    if not m or unit not in _UNIT_BYTES:
        raise CapacityError(f"看不懂 docker 给的大小：{text!r}")
    return int(float(m.group(1)) * _UNIT_BYTES[unit])


def parse_stats(text):
    """`docker stats --no-stream --format '{{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.PIDs}}'`"""
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        name, cpu, mem, pids = line.split("\t")
        rows.append({
            "name": name.strip(),
            "cpu": float(cpu.strip().rstrip("%")),
            "mem": parse_size(mem.split("/")[0]),
            "pids": int(pids.strip()),
        })
    return rows


def parse_limits(text):
    """`docker inspect --format '{{.HostConfig.Memory}}\\t{{.HostConfig.PidsLimit}}'`

    没设过上限时 Memory 是 0；PidsLimit 老 docker 给 0、新 docker 给 <nil>。都当 0。
    """
    mem, pids = (text.strip().split("\t") + ["0"])[:2]
    return {"mem_limit": int(mem) if mem.isdigit() else 0,
            "pids_limit": int(pids) if pids.isdigit() else 0}


def host_reserve(mem_total):
    return min(HOST_RESERVE_BYTES, mem_total // HOST_RESERVE_FRACTION)


def estimate(host, stats, limits=None, *, mem_limit, reserve):
    """纯算术，不碰 docker。数字全是字节，人数向下取整、不为负。

    硬上限按**每个容器自己的上限**累加，不是「常量 × 人数」：
    有人单独开到 3g 之后，两种算法就对不上了。没有上限的容器按 mem_limit 记
    （--apply-limits 补上之后它就是这个数）。mem_limit 只决定**还没开的**容器每个算多大，
    所以 what-if 换个数不会改写已开容器的账。
    """
    if mem_limit <= 0:
        raise CapacityError("mem_limit 必须大于 0 —— 没有上限就没有硬上限可算")
    limits = limits or {}
    budget = max(host["mem_total"] - reserve, 0)
    used = sum(r["mem"] for r in stats)
    active = [r["mem"] for r in stats if r["mem"] >= ACTIVE_THRESHOLD_BYTES]
    active_avg = sum(active) // len(active) if active else DEFAULT_ACTIVE_BYTES
    committed = sum(limits.get(r["name"], {}).get("mem_limit") or mem_limit for r in stats)
    hard_remaining = max(budget - committed, 0) // mem_limit
    return {
        "running": len(stats),
        "active": len(active),
        "idle": len(stats) - len(active),
        "active_avg": active_avg,
        "used": used,
        "budget": budget,
        "committed": committed,
        "hard_cap": len(stats) + hard_remaining,
        "hard_remaining": hard_remaining,
        "measured_remaining": max(budget - used, 0) // active_avg,
    }


# ---- 采集：下面这些才碰 docker ----------------------------------------------

def host_info():
    out = sandbox._docker("info", "--format", "{{json .}}")
    d = json.loads(out)
    return {"ncpu": d["NCPU"], "mem_total": d["MemTotal"],
            "os": d.get("OperatingSystem", "?"), "arch": d.get("Architecture", "?")}


def running_containers():
    """档案里有、且容器在跑的学员 → 容器名。只认档案，不用 mc-* 通配去猜。"""
    return [sandbox.container_name(r["student"]) for r in store.all_students()
            if sandbox.container_state(r["student"]) == "running"]


def container_stats(names):
    if not names:
        return []
    out = sandbox._docker("stats", "--no-stream", "--format",
                          "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}", *names)
    return parse_stats(out)


def container_limits(names):
    limits = {}
    for name in names:
        out = sandbox._docker("inspect", name, "--format",
                              "{{.HostConfig.Memory}}\t{{.HostConfig.PidsLimit}}")
        limits[name] = parse_limits(out)
    return limits


def disk_usage():
    """镜像只算一份；卷按每人一个持久卷汇总。"""
    # 用 image ls 而不是 image inspect 的 .Size：containerd 存储下后者是压缩后的
    # 内容大小（实测 1.1G vs 4.7G），和 `docker image ls` 给人看的对不上。
    image = sandbox._docker("image", "ls", sandbox.IMAGE, "--format", "{{.Size}}", check=False)
    df = json.loads(sandbox._docker("system", "df", "-v", "--format", "{{json .}}"))
    vols = [v for v in df.get("Volumes") or ()
            if v.get("Name", "").startswith("mc-") and v["Name"].endswith("-work")]
    return {
        "image": parse_size(image) if image else 0,
        "volumes": sum(parse_size(v["Size"]) for v in vols),
        "volume_count": len(vols),
    }


# ---- 渲染 --------------------------------------------------------------------

def _fmt(n):
    if n >= GiB:
        return f"{n / GiB:.1f} GiB"
    return f"{n / MiB:.0f} MiB"


def _width(s):
    """终端显示宽度：中文占两格。str.ljust 按字符数算，表头有中文就会歪。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _pad(s, width, align="<"):
    fill = " " * max(width - _width(s), 0)
    return fill + s if align == ">" else s + fill


def render(host, stats, limits, disk, est, *, mem_limit, reserve):
    default_limit = sandbox.mem_limit_bytes()
    limit_note = "" if mem_limit == default_limit else f"（--mem-limit 指定，默认 {sandbox.MEM_LIMIT}）"
    lines = [
        f"宿主机  {host['ncpu']} CPU · {_fmt(host['mem_total'])} 内存 · "
        f"{host.get('os', '?')} / {host.get('arch', '?')}",
        f"预留    {_fmt(reserve)}（系统、web 前端、网关）→ 可分配 {_fmt(est['budget'])}",
        f"上限    新开容器 {_fmt(mem_limit)} 内存、{sandbox.PIDS_LIMIT} 个进程{limit_note}",
        "",
    ]
    if stats:
        # 右对齐的数字列之后留两格再接左对齐的文字列，不然「进程」和「状态」会黏在一起
        cols = (("容器", 16, "<"), ("内存", 10, ">"), ("CPU", 8, ">"), ("进程", 6, ">"),
                ("  状态", 8, "<"), ("上限", 0, "<"))
        lines.append("".join(_pad(h, w, a) for h, w, a in cols).rstrip())
        for r in stats:
            lim = limits.get(r["name"], {})
            state = "活跃" if r["mem"] >= ACTIVE_THRESHOLD_BYTES else "空闲"
            capped = _fmt(lim["mem_limit"]) if lim.get("mem_limit") else "无"
            cells = (r["name"], _fmt(r["mem"]), f"{r['cpu']:.1f}%", str(r["pids"]),
                     "  " + state, capped)
            lines.append("".join(_pad(c, w, a) for c, (_, w, a) in zip(cells, cols)).rstrip())
    else:
        lines.append("没有在跑的学员容器")
    lines += [
        "",
        f"在跑    {est['running']} 个（活跃 {est['active']}，空闲 {est['idle']}），"
        f"合计占用 {_fmt(est['used'])}，活跃均值 {_fmt(est['active_avg'])}",
        f"硬上限  这台机器最多 {est['hard_cap']} 人同时在线（已开的按各自上限共 {_fmt(est['committed'])}，"
        f"新开的每个 {_fmt(mem_limit)}，全吃满也不会拖垮宿主机），还能再开 {est['hard_remaining']} 个",
        f"实测    按现在的平均占用还能再塞 {est['measured_remaining']} 个（乐观值，agent 都在跑时会向硬上限收敛）",
        f"磁盘    镜像 {_fmt(disk['image'])}（只算一份）· {disk['volume_count']} 个持久卷合计 {_fmt(disk['volumes'])}"
        + (f"，人均 {_fmt(disk['volumes'] // disk['volume_count'])}" if disk["volume_count"] else ""),
    ]
    unlimited = [n for n, lim in limits.items() if not lim.get("mem_limit")]
    if unlimited:
        lines += [
            "",
            f"⚠ {len(unlimited)} 个容器没有内存上限：{'、'.join(unlimited)}",
            "  它们是加上限之前开出来的。硬上限那行对它们不成立 —— 一个跑飞的进程能拖垮整台机器。",
            "  补上（即时生效，不重启、不丢会话）：sandctl capacity --apply-limits",
        ]
    return "\n".join(lines)


def report(mem_limit_spec=sandbox.MEM_LIMIT):
    """mem_limit_spec 是 docker 写法（2g）。传别的数就是 what-if：只改「新开的每个算多大」。"""
    names = running_containers()
    host = host_info()
    stats = container_stats(names)
    limits = container_limits(names)
    mem_limit = sandbox.mem_limit_bytes(mem_limit_spec)
    reserve = host_reserve(host["mem_total"])
    est = estimate(host, stats, limits, mem_limit=mem_limit, reserve=reserve)
    return render(host, stats, limits, disk_usage(), est, mem_limit=mem_limit, reserve=reserve)


def plan_limits(limits, stats, *, mem_limit):
    """纯算术：哪些容器要补上限、哪些现在不能补。返回 (要补的, [(不能补的, 当前占用)])。

    **当前占用已经超过上限的容器不能补**：cgroup 上限即时生效，用量超出就立刻 OOM，
    杀到 ttyd（PID 1）整个容器重启，学员的会话就没了 —— 和「不丢会话」的承诺相反。
    这种容器等它降下来再补，或者走 destroy --keep-volume + create。
    """
    usage = {r["name"]: r["mem"] for r in stats}
    todo, over = [], []
    for name, lim in limits.items():
        if lim["mem_limit"] and lim["pids_limit"]:
            continue
        if usage.get(name, 0) >= mem_limit:
            over.append((name, usage[name]))
        else:
            todo.append(name)
    return todo, over


def apply_missing_limits(mem_limit_spec=sandbox.MEM_LIMIT):
    """给没有上限的在跑容器补上。返回 (补过的容器名, [(跳过的容器名, 当前占用)])。"""
    names = running_containers()
    todo, over = plan_limits(container_limits(names), container_stats(names),
                             mem_limit=sandbox.mem_limit_bytes(mem_limit_spec))
    for name in todo:
        sandbox._docker("update", *sandbox.resource_limit_args(mem_limit_spec), name)
    return todo, over
