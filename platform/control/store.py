"""每名学员一个 JSON 文件的状态存储。

100 人/年、每周约 2 个新人 —— 不需要数据库。一个目录、一人一个文件，
出问题时 cat 一下就能看懂，也能手工改。

密钥不进状态文件：明文 key 单独落一个 0600 的文件。
"""
import json
import os
import re
import time

STATE_DIR = os.path.expanduser(
    os.environ.get("MICROCLASS_STATE", "~/.local/state/microclass"))
STUDENTS_DIR = os.path.join(STATE_DIR, "students")
SECRETS_DIR = os.path.join(STATE_DIR, "secrets")
EVIDENCE_DIR = os.path.join(STATE_DIR, "evidence")

# 学员 ID 会被拼进容器名、卷名和文件路径 —— 必须收紧
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,30}$")


class StoreError(RuntimeError):
    pass


def check_id(student):
    if not ID_RE.match(student or ""):
        raise StoreError(
            f"学员 ID {student!r} 不合法：只允许小写字母/数字/下划线/连字符，2–31 位，且以字母数字开头")
    return student


def _paths(student):
    check_id(student)
    return (os.path.join(STUDENTS_DIR, f"{student}.json"),
            os.path.join(SECRETS_DIR, f"{student}.key"))


def init_dirs():
    for d in (STUDENTS_DIR, SECRETS_DIR, EVIDENCE_DIR):
        os.makedirs(d, mode=0o700, exist_ok=True)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def exists(student):
    return os.path.exists(_paths(student)[0])


def load(student):
    path, _ = _paths(student)
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise StoreError(f"没有学员 {student}。先 sandctl create {student}") from None


def save(record):
    """写状态。永远返回新对象，不原地改传进来的那个。"""
    init_dirs()
    student = check_id(record["student"])
    path, _ = _paths(student)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)   # 原子替换，避免半截文件
    os.chmod(path, 0o600)
    return record


def update(student, **fields):
    return save({**load(student), **fields})


def all_students():
    init_dirs()
    out = []
    for name in sorted(os.listdir(STUDENTS_DIR)):
        if name.endswith(".json"):
            out.append(load(name[:-5]))
    return out


def put_key(student, token):
    init_dirs()
    _, keypath = _paths(student)
    fd = os.open(keypath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)
    return keypath


def get_key(student):
    _, keypath = _paths(student)
    try:
        with open(keypath) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def drop_key(student):
    _, keypath = _paths(student)
    try:
        os.remove(keypath)
        return True
    except FileNotFoundError:
        return False


def evidence_dir(student):
    check_id(student)
    d = os.path.join(EVIDENCE_DIR, student)
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def remove(student):
    path, _ = _paths(student)
    drop_key(student)
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
