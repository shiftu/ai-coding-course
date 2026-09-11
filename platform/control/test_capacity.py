#!/usr/bin/env python3
"""capacity 的离线测试：解析 docker 输出、容量算术、渲染。

不碰 docker：所有输入都是手写的 docker 文本。
跑法：python3 test_capacity.py
"""
import os
import pathlib
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="mc-capacity-test-")
os.environ["MICROCLASS_STATE"] = os.path.join(TMP, "state")   # 必须在 import store 之前
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import capacity  # noqa: E402
import sandbox   # noqa: E402

GiB = 1024 ** 3
MiB = 1024 ** 2


def test_parse_size_accepts_docker_binary_and_decimal_units():
    assert capacity.parse_size("950.4MiB") == int(950.4 * MiB)
    assert capacity.parse_size("5.772GiB") == int(5.772 * GiB)
    assert capacity.parse_size("4.66GB") == int(4.66 * 1000 ** 3)
    assert capacity.parse_size("14.69MB") == int(14.69 * 1000 ** 2)
    assert capacity.parse_size("0B") == 0
    assert capacity.parse_size("  19MiB ") == 19 * MiB


def test_parse_size_rejects_garbage():
    for bad in ("", "N/A", "abc", "12", "12XB"):
        try:
            capacity.parse_size(bad)
        except capacity.CapacityError:
            continue
        raise AssertionError(f"{bad!r} 应该报错")


def test_parse_stats_reads_docker_stats_lines():
    text = ("mc-stu-x\t4.83%\t950.4MiB / 5.772GiB\t145\n"
            "mc-stu-jt\t0.00%\t19MiB / 5.772GiB\t3\n")
    rows = capacity.parse_stats(text)
    assert [r["name"] for r in rows] == ["mc-stu-x", "mc-stu-jt"]
    assert rows[0]["mem"] == int(950.4 * MiB)
    assert rows[0]["cpu"] == 4.83
    assert rows[0]["pids"] == 145
    assert rows[1]["pids"] == 3
    assert capacity.parse_stats("") == []


def test_parse_limits_reads_inspect_output():
    # docker inspect --format '{{.HostConfig.Memory}}\t{{.HostConfig.PidsLimit}}'
    assert capacity.parse_limits("2147483648\t512") == {"mem_limit": 2 * GiB, "pids_limit": 512}
    # 没设过：Memory 是 0，PidsLimit 老版本是 0、新版本是 <nil>
    assert capacity.parse_limits("0\t0") == {"mem_limit": 0, "pids_limit": 0}
    assert capacity.parse_limits("0\t<nil>") == {"mem_limit": 0, "pids_limit": 0}


def _stats(*mems):
    return [{"name": f"mc-stu-{i}", "cpu": 0.0, "mem": m, "pids": 3} for i, m in enumerate(mems)]


def test_estimate_splits_active_from_idle_by_threshold():
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    stats = _stats(950 * MiB, 19 * MiB, 21 * MiB)
    r = capacity.estimate(host, stats, mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["running"] == 3
    assert r["active"] == 1
    assert r["idle"] == 2
    assert r["active_avg"] == 950 * MiB


def test_estimate_hard_cap_is_budget_over_limit():
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    r = capacity.estimate(host, _stats(), mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["budget"] == 56 * GiB
    assert r["hard_cap"] == 28          # (64-8)/2
    assert r["hard_remaining"] == 28    # 一个都没开


def test_estimate_hard_remaining_subtracts_running_containers():
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    r = capacity.estimate(host, _stats(950 * MiB, 19 * MiB, 21 * MiB), mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["hard_remaining"] == 25    # 28 - 3 个已开（每个都可能吃满 2g）


def _limits(**per_name):
    return {n: {"mem_limit": m, "pids_limit": 512 if m else 0} for n, m in per_name.items()}


def test_estimate_charges_each_container_its_own_limit_when_limits_differ():
    # 一个 3g、一个 2g、一个没上限（按新开的上限估）：已承诺 3+2+2 = 7 GiB
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    stats = _stats(100 * MiB, 100 * MiB, 100 * MiB)
    limits = {"mc-stu-0": {"mem_limit": 3 * GiB, "pids_limit": 512},
              "mc-stu-1": {"mem_limit": 2 * GiB, "pids_limit": 512},
              "mc-stu-2": {"mem_limit": 0, "pids_limit": 0}}
    r = capacity.estimate(host, stats, limits=limits, mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["committed"] == 7 * GiB
    assert r["hard_remaining"] == (56 - 7) // 2      # 24
    assert r["hard_cap"] == 3 + 24


def test_estimate_with_uniform_limits_matches_the_simple_formula():
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    stats = _stats(100 * MiB, 100 * MiB)
    limits = {"mc-stu-0": {"mem_limit": 2 * GiB, "pids_limit": 512},
              "mc-stu-1": {"mem_limit": 2 * GiB, "pids_limit": 512}}
    r = capacity.estimate(host, stats, limits=limits, mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["hard_cap"] == 28 and r["hard_remaining"] == 26


def test_estimate_what_if_limit_changes_only_new_containers():
    # what-if 3g：已开的两个还是 2g，只有还没开的按 3g 算
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    stats = _stats(100 * MiB, 100 * MiB)
    limits = _limits(**{"mc-stu-0": 2 * GiB, "mc-stu-1": 2 * GiB})
    r = capacity.estimate(host, stats, limits=limits, mem_limit=3 * GiB, reserve=8 * GiB)
    assert r["committed"] == 4 * GiB
    assert r["hard_remaining"] == (56 - 4) // 3      # 17


def test_estimate_measured_remaining_uses_active_average():
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    r = capacity.estimate(host, _stats(1 * GiB, 20 * MiB), mem_limit=2 * GiB, reserve=8 * GiB)
    used = 1 * GiB + 20 * MiB
    assert r["used"] == used
    assert r["measured_remaining"] == (56 * GiB - used) // (1 * GiB)   # 55


def test_estimate_without_active_containers_falls_back_to_default_active_size():
    host = {"ncpu": 8, "mem_total": 64 * GiB}
    r = capacity.estimate(host, _stats(19 * MiB), mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["active_avg"] == capacity.DEFAULT_ACTIVE_BYTES
    assert r["measured_remaining"] == (56 * GiB - 19 * MiB) // capacity.DEFAULT_ACTIVE_BYTES


def test_estimate_never_goes_negative_on_small_host():
    host = {"ncpu": 5, "mem_total": 6 * GiB}
    r = capacity.estimate(host, _stats(3 * GiB), mem_limit=2 * GiB, reserve=8 * GiB)
    assert r["budget"] == 0
    # 已经在跑的那 1 个照实算进硬上限（它就在那儿），但再也开不了新的
    assert r["hard_cap"] == 1 and r["hard_remaining"] == 0 and r["measured_remaining"] == 0


def test_estimate_rejects_zero_limit():
    try:
        capacity.estimate({"ncpu": 1, "mem_total": GiB}, [], mem_limit=0, reserve=0)
    except capacity.CapacityError:
        return
    raise AssertionError("mem_limit=0 应该报错")


def test_host_reserve_caps_at_fixed_amount_on_big_hosts_and_scales_on_small():
    assert capacity.host_reserve(64 * GiB) == 4 * GiB
    assert capacity.host_reserve(6 * GiB) == int(1.5 * GiB)


def test_pad_counts_cjk_as_double_width():
    assert capacity._pad("容器", 8) == "容器    "        # 2 个汉字 = 4 格，补 4 个空格
    assert capacity._pad("mc-stu-x", 8) == "mc-stu-x"
    assert capacity._pad("内存", 8, ">") == "    内存"
    assert capacity._pad("太长的一个名字", 4) == "太长的一个名字"  # 不截断


def test_plan_limits_skips_containers_already_over_the_limit():
    limits = {"mc-stu-a": {"mem_limit": 0, "pids_limit": 0},          # 要补
              "mc-stu-b": {"mem_limit": 0, "pids_limit": 0},          # 已超上限，补了会 OOM
              "mc-stu-c": {"mem_limit": 2 * GiB, "pids_limit": 512},  # 已经有了
              "mc-stu-d": {"mem_limit": 2 * GiB, "pids_limit": 0}}    # 只有一半也算缺
    stats = [{"name": "mc-stu-a", "cpu": 0.0, "mem": 900 * MiB, "pids": 100},
             {"name": "mc-stu-b", "cpu": 0.0, "mem": 2 * GiB + 1, "pids": 100},
             {"name": "mc-stu-c", "cpu": 0.0, "mem": 10 * MiB, "pids": 3}]
    todo, over = capacity.plan_limits(limits, stats, mem_limit=2 * GiB)
    assert todo == ["mc-stu-a", "mc-stu-d"]
    assert over == [("mc-stu-b", 2 * GiB + 1)]


def test_resource_limit_args_are_hard_limits():
    args = sandbox.resource_limit_args()
    # swap 必须等于 memory，否则 --memory 只是软的：容器还能再吃同样大小的 swap
    assert args[args.index("--memory") + 1] == sandbox.MEM_LIMIT
    assert args[args.index("--memory-swap") + 1] == sandbox.MEM_LIMIT
    assert args[args.index("--pids-limit") + 1] == str(sandbox.PIDS_LIMIT)
    # docker run 的 2g / 512m 写法（和 stats 输出的 MiB/GiB 不是一套）
    assert sandbox.mem_limit_bytes("2g") == 2 * GiB
    assert sandbox.mem_limit_bytes("512m") == 512 * MiB
    assert sandbox.mem_limit_bytes("1073741824") == GiB
    assert sandbox.mem_limit_bytes() == sandbox.mem_limit_bytes(sandbox.MEM_LIMIT)


def test_resource_limit_args_accept_a_custom_limit_and_keep_swap_equal():
    args = sandbox.resource_limit_args("3g")
    assert args[args.index("--memory") + 1] == "3g"
    assert args[args.index("--memory-swap") + 1] == "3g"
    assert args[args.index("--pids-limit") + 1] == str(sandbox.PIDS_LIMIT)


def test_mem_limit_bytes_rejects_garbage():
    for bad in ("", "abc", "2gb", "-1g", "0", "1.5x"):
        try:
            sandbox.mem_limit_bytes(bad)
        except sandbox.SandboxError:
            continue
        raise AssertionError(f"{bad!r} 应该报错")


def test_plan_limits_uses_the_given_limit_for_the_over_check():
    limits = {"mc-stu-a": {"mem_limit": 0, "pids_limit": 0}}
    stats = [{"name": "mc-stu-a", "cpu": 0.0, "mem": 2 * GiB + 1, "pids": 3}]
    assert capacity.plan_limits(limits, stats, mem_limit=2 * GiB) == ([], [("mc-stu-a", 2 * GiB + 1)])
    assert capacity.plan_limits(limits, stats, mem_limit=3 * GiB) == (["mc-stu-a"], [])


def test_render_mentions_both_estimates_and_unlimited_containers():
    host = {"ncpu": 8, "mem_total": 64 * GiB, "os": "Ubuntu", "arch": "aarch64"}
    stats = _stats(950 * MiB, 19 * MiB)
    limits = {"mc-stu-0": {"mem_limit": 2 * GiB, "pids_limit": 512},
              "mc-stu-1": {"mem_limit": 0, "pids_limit": 0}}
    disk = {"image": 4.66 * 1000 ** 3, "volumes": 1.3 * GiB, "volume_count": 2}
    est = capacity.estimate(host, stats, mem_limit=2 * GiB, reserve=8 * GiB)
    out = capacity.render(host, stats, limits, disk, est, mem_limit=2 * GiB, reserve=8 * GiB)
    assert "硬上限" in out and "实测" in out
    assert "mc-stu-1" in out and "没有内存上限" in out
    assert "mc-stu-0" in out.split("没有内存上限")[0]   # 表格里两个都在
    assert "--apply-limits" in out


def test_render_has_no_unlimited_warning_when_all_limited():
    host = {"ncpu": 8, "mem_total": 64 * GiB, "os": "Ubuntu", "arch": "aarch64"}
    stats = _stats(19 * MiB)
    limits = {"mc-stu-0": {"mem_limit": 2 * GiB, "pids_limit": 512}}
    est = capacity.estimate(host, stats, mem_limit=2 * GiB, reserve=8 * GiB)
    out = capacity.render(host, stats, limits, {"image": 0, "volumes": 0, "volume_count": 0},
                          est, mem_limit=2 * GiB, reserve=8 * GiB)
    assert "没有内存上限" not in out


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {name}\n       {type(e).__name__}: {e}")
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {len(tests) - failed}，失败 {failed}")
    sys.exit(1 if failed else 0)
