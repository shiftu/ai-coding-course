"""容器这一层：卷、端口、ttyd、环境变量注入。

一名学员 = 一个容器 + 一个持久卷 + 一个只监听回环的 ttyd 端口。
不上 K8s、不做预约调度 —— 峰值并发 30，`docker run` 足够（设计文档 §6）。
"""
import pathlib
import secrets
import socket
import subprocess

import store

IMAGE = "microclass/sandbox:current"
# 容器看宿主机的地址。colima(vz+gvproxy) 下就是 192.168.5.2，spike 已实测。
HOST_FROM_CONTAINER = "192.168.5.2"
GATEWAY_PORT = 7421
TTYD_INNER_PORT = 7681
PORT_RANGE = range(7801, 7900)

# 每个学员容器的硬上限。这两个数是容量估算的分母：宿主机能开多少人 =
# (总内存 − 预留) / MEM_LIMIT（见 capacity.py）。没有上限时容量只是个平均数，
# 一个跑飞的进程就能把整台机器拖垮，其他 29 个人一起掉线。
#
# 2g 的依据：实测活跃沙盒（claude + hermes 两个 agent 同时在跑）约 950 MiB，
# 空闲只有 ttyd + bash 约 20 MiB；2g 给 pytest / npm install 的尖峰留了一倍余量。
# 512 个进程：活跃沙盒实测 145 个，fork 炸弹和失控的子进程树到这里就停。
MEM_LIMIT = "2g"
PIDS_LIMIT = 512
_UNITS = {"b": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}


def mem_limit_bytes(limit=MEM_LIMIT):
    """docker 风格的 2g / 512m / 纯字节数 → 字节。给 capacity 当分母用。

    这也是 --mem-limit 的校验：认不出来就报错，别把 '2gb' 之类的原样递给 docker
    让它在起容器的半路上失败。
    """
    s = (limit or "").strip().lower()
    unit = s[-1] if s and s[-1] in _UNITS else "b"
    num = s[:-1] if s and s[-1] in _UNITS else s
    try:
        n = int(float(num) * _UNITS[unit])
    except ValueError:
        n = 0
    if n <= 0:
        raise SandboxError(f"内存上限 {limit!r} 看不懂 —— 写成 2g / 512m 这种，且必须大于 0")
    return n


def resource_limit_args(mem_limit=MEM_LIMIT):
    """docker run / docker update 共用的那几个参数。

    --memory-swap 必须等于 --memory：不写的话 docker 默认允许再吃同样大小的 swap，
    --memory 就成了软的，容量算术随之失效。所以两者永远从同一个 mem_limit 出。
    """
    mem_limit_bytes(mem_limit)        # 校验
    return ["--memory", mem_limit, "--memory-swap", mem_limit,
            "--pids-limit", str(PIDS_LIMIT)]


class SandboxError(RuntimeError):
    pass


def container_name(student):
    return f"mc-{store.check_id(student)}"


def volume_name(student):
    return f"mc-{store.check_id(student)}-work"


def _docker(*args, check=True, capture=True):
    r = subprocess.run(["docker", *args], capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise SandboxError(f"docker {' '.join(args[:3])} 失败：{(r.stderr or r.stdout).strip()}")
    return (r.stdout or "").strip()


def container_state(student):
    """running / exited / absent"""
    out = _docker("ps", "-a", "--filter", f"name=^{container_name(student)}$",
                  "--format", "{{.State}}", check=False)
    return out.splitlines()[0].strip() if out.strip() else "absent"


def _port_taken(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def pick_port(used):
    for p in PORT_RANGE:
        if p not in used and not _port_taken(p):
            return p
    raise SandboxError(f"{PORT_RANGE.start}–{PORT_RANGE.stop} 里没有空闲端口了")


# ttyd 挂在这个前缀下，而不是根路径。
# 原因：web 前端要把它反代出去，而 ttyd 的页面里引用的是**绝对路径**
# （/ws、/token）。挂在根上时，反代到 /term/xxx/ 会让这些资源 404。
# 用固定前缀（不是每人一个）是故意的：学员身份从 session cookie 取，
# 不从 URL 取 —— URL 里没有可篡改的身份。
TTYD_BASE_PATH = "/t"

_LOCK = pathlib.Path(__file__).resolve().parents[1] / "sandbox" / "versions.lock"


def locked(key, default=""):
    """从 versions.lock 读一项。模型和工具版本同属单版本策略，
    不在两处各写一份 —— 那样迟早会漂。"""
    try:
        for line in _LOCK.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return default


def gateway_url(host=HOST_FROM_CONTAINER, port=GATEWAY_PORT):
    return f"http://{host}:{port}"


UNKNOWN_STAMP = "unknown"
# 镜像还在本地但没有任何 tag 指着它（被后来的构建顶掉了名字）
UNTAGGED = "<已无 tag>"
# 连镜像本身都不在本地了：容器还在跑，但那份镜像已经没法再开一个出来
IMAGE_GONE = "<镜像已不在本地>"


def _stamp_from_env(env_lines):
    """从 docker 吐出来的 Env 数组里挑出构建戳。"""
    for line in env_lines or ():
        if line.startswith("MICROCLASS_IMAGE_STAMP="):
            return line.split("=", 1)[1] or UNKNOWN_STAMP
    # 老镜像没烙戳（这个字段是后加的）。说"没有"，不要编一个。
    return UNKNOWN_STAMP


def _pick_tag(repo_tags):
    """一堆 RepoTags 里挑那个带戳的。:current 每次构建都重指，记它等于没记。"""
    for tag in repo_tags or ():
        if tag.startswith("microclass/sandbox:") and not tag.endswith(":current"):
            return tag
    return (repo_tags or [IMAGE])[0]


def image_identity(student=None, image=IMAGE):
    """镜像身份三件套：tag、image_id、build_stamp。

    档案里只记一个 tag 是不够的，「回溯这人当时用的是哪套环境」会落空，
    两条路都堵不住：

      ① tag 曾经只哈希 versions.lock —— 改一行 rootfs 重建，内容变了 tag 没变，
         同一个 tag 在不同时间指向过两个不同的环境。（已由 sandbox/stamp.sh 修掉。）
      ② 就算戳算得再准，tag 仍然只是宿主机上一个可以随手改掉的标签。
         `docker tag` 一句话就能让它指向别的镜像，而档案毫不知情。

    所以真正当身份用的是 image_id —— docker 自己算的内容 sha256，改不了、
    也不会重名。build_stamp 是它的可读对照：拿着戳能回到当时那份
    versions.lock + Dockerfile + rootfs。

    给了 student 且容器还在，就以**容器实际在跑的那个镜像**为准 —— 那是地面真相，
    比"现在 :current 指着谁"可靠：学员的容器是几周前起的，:current 早漂走了。
    """
    if student is not None and container_state(student) != "absent":
        out = _docker("inspect", container_name(student), "--format",
                      "{{.Image}}\t{{.Config.Image}}\t{{join .Config.Env \"\\n\"}}",
                      check=False)
        if out:
            image_id, _config_image, env_blob = (out.split("\t", 2) + ["", ""])[:3]
            # .Config.Image 是 docker run 当时写下的那个字符串，几乎总是 :current，
            # 拿它当档案是自欺欺人 —— 真正的 tag 从 image_id 反查。
            probe = _docker("image", "inspect", image_id, "--format",
                            "{{join .RepoTags \",\"}}|", check=False)
            if not probe:
                # 镜像记录已经不在本地了。**这不是异常，是常态**：老的 tag 方案
                # 只哈希 versions.lock，改 rootfs 重建会把同名 tag 挪走，
                # 原来那个镜像就此变成无名氏，随手一次 prune 就没了。
                # 容器还在跑（层还被引用着），但你再也开不出第二个一样的来。
                # 说清楚它没了，好过报一个查无此物的 tag。
                tag = IMAGE_GONE
            else:
                taglist = [t for t in probe.rstrip("|").split(",") if t]
                tag = _pick_tag(taglist) if taglist else UNTAGGED
            return {
                "image": tag,
                "image_id": image_id,
                "image_stamp": _stamp_from_env(env_blob.split("\n")),
                "source": "container",
            }

    out = _docker("image", "inspect", image, "--format",
                  "{{.Id}}\t{{join .RepoTags \",\"}}\t{{join .Config.Env \"\\n\"}}",
                  check=False)
    if not out:
        # 镜像都不在本地，别硬凑一个身份出来 —— 记 unknown，让 image-audit 报出来。
        return {"image": image, "image_id": UNKNOWN_STAMP,
                "image_stamp": UNKNOWN_STAMP, "source": "missing"}
    image_id, tags, env_blob = (out.split("\t", 2) + ["", ""])[:3]
    return {
        "image": _pick_tag([t for t in tags.split(",") if t]),
        "image_id": image_id,
        "image_stamp": _stamp_from_env(env_blob.split("\n")),
        "source": "image",
    }


def create(student, *, mode, track, api_key, port, ttyd_user, ttyd_pass, image=IMAGE,
           record=False, mem_limit=MEM_LIMIT):
    """起一个学员容器。ttyd 是 PID 1，每次连接 spawn 一个登录 shell。

    record=True 让课程模式也录屏（profile.d 里的守卫看 MICROCLASS_RECORD）。
    测评模式不看这个开关，一律录。
    mem_limit 默认 MEM_LIMIT；单独给某人开大时传进来，容量报告按每个容器的实际上限累加。
    """
    name = container_name(student)
    model = locked("MODEL", "charaboard/deepseek-v4-flash")
    # codex 单独换了模型（versions.lock 里 CODEX_MODEL，那里写了为什么）。
    # 没配就回落到统一模型 —— 删掉那行 lock 配置不需要改这里。
    codex_model = locked("CODEX_MODEL", "") or model
    if container_state(student) != "absent":
        raise SandboxError(f"容器 {name} 已存在。先 sandctl destroy {student}")

    _docker("volume", "create", volume_name(student))
    gw = gateway_url()

    env = {
        # 网关：学员不填任何 key，claude/codex 直接可用
        "MICROCLASS_GATEWAY": gw,
        "ANTHROPIC_BASE_URL": gw,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
        "OPENAI_BASE_URL": f"{gw}/v1",
        "OPENAI_API_KEY": api_key,
        # 家目录落到持久卷上：代码、claude 会话记录、hermes 状态都跟着人走
        "HOME": "/workspace",
        "CLAUDE_CONFIG_DIR": "/workspace/.claude",
        "HERMES_HOME": "/workspace/.hermes",
        "MICROCLASS_MODEL": model,
        "MICROCLASS_CODEX_MODEL": codex_model,
        # /opt/hermes/bin/hermes 是个降权 shim，会切到 uid 10000。而 $HOME 在
        # 持久卷上是 root:root 755 —— 降权之后它连自己的 HERMES_HOME 都建不出来，
        # 报 Errno 13。那个 shim 是为了和 s6 监管的 gateway 进程对齐 uid，
        # 我们的容器 PID 1 是 ttyd，没有那个进程，所以用它自带的 opt-out 关掉。
        "HERMES_DOCKER_EXEC_AS_ROOT": "1",
        "MICROCLASS_STUDENT": student,
        "MICROCLASS_MODE": mode,
    }
    if track:
        env["MICROCLASS_TRACK"] = track
    if record:
        env["MICROCLASS_RECORD"] = "1"

    args = ["run", "-d", "--name", name, "--restart", "unless-stopped",
            *resource_limit_args(mem_limit),
            # 只绑回环。对外由 web 前端反代，容器自己绝不暴露到 0.0.0.0
            "-p", f"127.0.0.1:{port}:{TTYD_INNER_PORT}",
            "-v", f"{volume_name(student)}:/workspace",
            "-v", f"{store.evidence_dir(student)}:/evidence",
            "--entrypoint", "/usr/local/bin/ttyd"]
    for k, v in env.items():
        args += ["-e", f"{k}={v}"]
    args += [image,
             "-p", str(TTYD_INNER_PORT),
             "-b", TTYD_BASE_PATH,
             "-c", f"{ttyd_user}:{ttyd_pass}",
             "-W",                       # 可写，否则终端没法输入
             "-t", "titleFixed=AI 微课堂",
             "/bin/bash", "-l"]
    _docker(*args)
    return name


# 测评任务的真源。仿真器 simulate.py 一直在 docker cp 这个目录，但**交付路径里
# 从来没有这一步** —— 真走 sandctl create 开出来的测评号，学员登进去 /workspace
# 是空的：一个测评沙盒没有测评任务。之前没暴露，是因为唯一跑过测评的那个号
# 是仿真器起的，任务是仿真器放进去的。
_CURRICULUM = pathlib.Path(__file__).resolve().parents[2] / "curriculum" / "assessment"


def task_dir(track):
    """轨道 → 任务目录名。A→task-a。B/C 变体（反作弊）就位后同样走这里。"""
    return f"task-{(track or 'a').lower()}"


def _issue_file(track):
    """这一轨的 Issue 正文。

    **找不到就报错，绝不静默跳过。**原先这里写死 ISSUE-7.md 且带 is_file() 守卫，
    轨道 B 的学员会拿到一个没有 Issue 的仓库 —— 任务本身丢了，而交付流程一路绿灯。
    A 的文件叫 ISSUE-7.md（正文里就是 Issue #7），B/C 按变体名，两种都认。
    """
    t = (track or "a").lower()
    for name in (f"ISSUE-{t.upper()}.md", "ISSUE-7.md" if t == "a" else None):
        if name and (_CURRICULUM / name).is_file():
            return _CURRICULUM / name
    raise SandboxError(
        f"轨道 {track!r} 没有 Issue 正文 —— 找过 ISSUE-{t.upper()}.md"
        f"{'、ISSUE-7.md' if t == 'a' else ''}。学员会拿到一个没有任务的仓库。")


def check_task_ready(track):
    """这一轨的题齐不齐：仓库 + Issue 正文。返回 (仓库路径, Issue 路径)。

    **开号前先跑这个。**先建容器、发 key、存档案，再发现没题可投，
    留下的是一个半成品学员加一把活着的网关 key，得人工清理。
    """
    src = _CURRICULUM / task_dir(track)
    if not src.is_dir():
        raise SandboxError(f"轨道 {track!r} 没有测评仓库（找不到 {src}）—— 先把题写出来再开号。")
    return src, _issue_file(track)


def seed_task(student, track, *, force=False):
    """把测评任务投进容器，并做初始提交。

    初始提交不是可选项：批改的证据源 ② 是 git 历史，要靠"和初始提交的 diff"
    看出学员到底改了什么。没有基线提交，那条证据整条哑掉。
    """
    name = task_dir(track)
    src, issue = check_task_ready(track)

    dst = f"/workspace/{name}"
    rc, _ = exec_in(student, f"test -e {dst}", login=False)
    if rc == 0:
        if not force:
            raise SandboxError(
                f"{dst} 已存在。重投会盖掉学员已经写的东西 —— 确认要重来再加 --force")
        exec_in(student, f"rm -rf {dst}", login=False)

    c = container_name(student)
    # docker cp 到一个**不存在**的目标路径才会展开成该目录；目标已存在时会塞进去
    # 变成 task-a/task-a。上面的 test -e 守卫同时也是在守这一点。
    _docker("cp", str(src), f"{c}:{dst}")
    _docker("cp", str(issue), f"{c}:{dst}/{issue.name}")

    rc, out = exec_in(student, (
        f"cd {dst} && git init -q && git add -A && "
        "git -c user.email=stu@microclass -c user.name=stu "
        "commit -qm '初始提交（平台预置）' && git log --oneline | head -1"))
    if rc != 0:
        raise SandboxError(f"{dst} 预置了但 git 没跑起来 —— 证据源 ② 会哑：{out.strip()}")
    return dst, out.strip()


def ensure_task(student, track):
    """确保这一轨的题在容器里就位。返回 (路径, 基线提交, 是不是这次投的)。

    和 seed_task 的区别是语义：seed_task 是"投一次题"，见到目标已存在就拒绝
    （防止盖掉学员写的东西）；ensure_task 是"确认题在不在"，已经在就认它。

    **为什么需要这个**：`destroy --keep-volume` + `create` 是把学员换到新镜像的
    唯一路径，而卷里的 /workspace/task-a 正是要保住的那份成果。create 里直接调
    seed_task 会撞上那道守卫报错退出 —— 容器已经起来、档案已经存好、新 key 已经
    发了，却停在 selfcheck 之前，命令看着像失败，实际是个没验收的半成品。

    **已经在也要验基线。** 只查目录在会漏掉"有题但没基线提交"，那种情况证据源 ②
    照样整条哑掉（microclass-doctor 里同款检查，理由见 sandbox/README）。
    这时不能静默跳过，必须报出来人工处置。
    """
    dst = f"/workspace/{task_dir(track)}"
    rc, _ = exec_in(student, f"test -e {dst}", login=False)
    if rc != 0:
        seeded_dst, head = seed_task(student, track)
        return seeded_dst, head, True

    rc, out = exec_in(student, f"cd {dst} && git log --oneline -1")
    if rc != 0:
        raise SandboxError(
            f"{dst} 在，但没有基线提交 —— 批改的证据源 ② 是「和基线的 diff」，"
            f"没有基线那条证据整条哑。人工确认里面的东西还要不要，"
            f"要就补一个提交，不要就 sandctl seed {student} --force 重投。"
            f"（git 说：{out.strip()}）")
    return dst, out.strip(), False


def doctor(student):
    """运行期体检：每件工具真的发一次请求。必须用登录 shell（PATH 见 profile.d）。"""
    p = subprocess.run(
        ["docker", "exec", container_name(student), "bash", "-lc", "microclass-doctor"],
        capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def apply_limits(student, mem_limit=MEM_LIMIT):
    """给一个已经在跑的容器补上资源上限（加上限之前开出来的老容器用）。

    docker update 对运行中的容器即时生效，不用重启、不丢会话 —— 前提是当前占用
    没超过新上限，超过会立刻 OOM。调用方（capacity.plan_limits）负责先查这一点。
    """
    _docker("update", *resource_limit_args(mem_limit), container_name(student))


def start(student):
    _docker("start", container_name(student))


def stop(student):
    _docker("stop", container_name(student), check=False)


def destroy(student, *, keep_volume=False):
    _docker("rm", "-f", container_name(student), check=False)
    if not keep_volume:
        _docker("volume", "rm", volume_name(student), check=False)


def exec_in(student, script, *, login=True):
    """在学员容器里跑一段 shell。默认登录 shell —— 学员看到的就是它。"""
    flag = "-lc" if login else "-c"
    r = subprocess.run(
        ["docker", "exec", container_name(student), "/bin/bash", flag, script],
        capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def selfcheck(student):
    return exec_in(student, "microclass-selfcheck")


def new_password():
    return secrets.token_urlsafe(15)
