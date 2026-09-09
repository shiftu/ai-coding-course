"""读取依赖清单。

线上版本会调 GitHub API 去核对上游仓库里真实的 LICENSE 文件（清单里的
license 字段是打包方自己填的，不总准）。本地和 CI 一律走离线清单，
免得每审一次就烧掉一轮 API 限额。
"""
import json
import os
import pathlib

MANIFEST = pathlib.Path(__file__).parent.parent / "sample_data" / "dependencies.json"

REQUIRED_FIELDS = ("name", "version", "license", "direct")

# 一开始只审直接依赖，后来 CI 那边希望连间接引入的一起看，就把默认值翻过来了。
DEFAULT_INCLUDE_TRANSITIVE = True


def normalize_entry(entry):
    """校验一条依赖记录，返回字段齐全的新拷贝。

    清单是人手维护的，缺字段是常事。在入口一次性拦掉，
    后面 classify / report 就不用到处补 if。
    """
    missing = [field for field in REQUIRED_FIELDS if field not in entry]
    if missing:
        raise ValueError(f"依赖记录缺字段 {missing}：{entry}")
    return {
        "name": entry["name"],
        "version": entry["version"],
        "license": entry["license"],
        "direct": bool(entry["direct"]),
    }


def load_manifest(path=None):
    """读依赖清单，返回规范化后的列表。"""
    if os.environ.get("DEP_AUDIT_OFFLINE", "1") != "1":
        raise NotImplementedError("在线核对上游 LICENSE 尚未接入，见 Issue #12")
    raw = json.loads(pathlib.Path(path or MANIFEST).read_text(encoding="utf-8"))
    return [normalize_entry(entry) for entry in raw]


def scan_dependencies(path=None, include_transitive=None):
    """列出这次要审的依赖。

    include_transitive 不传时沿用 DEFAULT_INCLUDE_TRANSITIVE。
    """
    if include_transitive is None:
        include_transitive = DEFAULT_INCLUDE_TRANSITIVE
    deps = load_manifest(path)
    if include_transitive:
        return deps
    return [dep for dep in deps if dep["direct"]]
