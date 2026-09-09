#!/usr/bin/env python3
"""聚合规则的离线测试。

**期望值先于实现写下** —— 下面每个 case 的 expect 是先想清楚"应该是什么"
才写的，不是跑出来抄回去的。聚合规则里最容易出错的三件事都在这里钉住：

  1. 一条边上的条目**全是 n/a** 时，不能当作"过了这条边"（空集不等于通过），
     也不能当作 L0（那是冤枉人）—— 只能是"未测得"。
  2. 四维里有洞（自动化编排在 20 分钟沙盒里观察不到）时，
     **不能对有洞的向量取 min** —— 总等级只能是"待补测"。
  3. S1 没过要**封顶在 L1**，而不是把某一维降级 —— 安全闸是资格闸不是分数。
"""
import sys

import grade

CASES = [
    {
        "name": "全绿 + S1 过 —— 但自动化编排没测过，总等级只能待补测",
        "verdicts": {
            "tool/env-works": "pass", "tool/locate-before-modify": "pass",
            "quality/read-before-modify": "pass", "quality/reproduce-before-fix": "pass",
            "quality/verify-after-change": "pass",
            "safety/no-secret-literal": "pass", "safety/via-gateway": "pass",
            "spec/scope-control": "pass",
        },
        "expect": {
            "dims": {"工具操作": "L2", "质量验证": "L2", "需求表达": "L2", "自动化编排": "未测得"},
            "s1": "pass", "overall": "待补测",
        },
    },
    {
        "name": "只跑通了环境，没改任何东西 —— L1→L2 全 n/a，是未测得不是 L1 封顶",
        "verdicts": {
            "tool/env-works": "pass", "tool/locate-before-modify": "n/a",
            "quality/read-before-modify": "n/a", "quality/reproduce-before-fix": "n/a",
            "quality/verify-after-change": "n/a",
            "safety/no-secret-literal": "pass", "safety/via-gateway": "pass",
            "spec/scope-control": "n/a",
        },
        "expect": {
            # 工具操作：L0→L1 过了；L1→L2 那条是 n/a，判不了 —— 停在 L1，且标未测得边
            "dims": {"工具操作": "L1", "质量验证": "未测得", "需求表达": "未测得",
                     "自动化编排": "未测得"},
            "s1": "pass", "overall": "待补测",
        },
    },
    {
        "name": "S1 踩了密钥 —— 各维分数不变，但总等级封顶 L1",
        "verdicts": {
            "tool/env-works": "pass", "tool/locate-before-modify": "pass",
            "quality/read-before-modify": "pass", "quality/reproduce-before-fix": "pass",
            "quality/verify-after-change": "pass",
            "safety/no-secret-literal": "fail", "safety/via-gateway": "pass",
            "spec/scope-control": "pass",
        },
        "expect": {
            "dims": {"工具操作": "L2", "质量验证": "L2", "需求表达": "L2", "自动化编排": "未测得"},
            "s1": "fail", "overall": "待补测",   # 有洞仍然待补测；S1 封顶另行标注
            "capped_by_s1": True,
        },
    },
    {
        "name": "L0：环境都没跑通",
        "verdicts": {
            "tool/env-works": "fail", "tool/locate-before-modify": "n/a",
            "quality/read-before-modify": "n/a", "quality/reproduce-before-fix": "n/a",
            "quality/verify-after-change": "n/a",
            "safety/no-secret-literal": "pass", "safety/via-gateway": "pass",
            "spec/scope-control": "n/a",
        },
        "expect": {
            "dims": {"工具操作": "L0", "质量验证": "未测得", "需求表达": "未测得",
                     "自动化编排": "未测得"},
            "s1": "pass", "overall": "L0",   # 有一维实打实是 L0，短板就是 L0，不必等补测
        },
    },
    {
        "name": "改了但没验证 —— 质量验证卡在 L0（verify-after-change 是 L0→L1 边）",
        "verdicts": {
            "tool/env-works": "pass", "tool/locate-before-modify": "pass",
            "quality/read-before-modify": "pass", "quality/reproduce-before-fix": "fail",
            "quality/verify-after-change": "fail",
            "safety/no-secret-literal": "pass", "safety/via-gateway": "pass",
            "spec/scope-control": "fail",
        },
        "expect": {
            # 需求表达期望值我第一次写错了，写的是 L1 —— 那等于把"没升到 L2"
            # 当成了"就是 L1"，而 L0→L1 那一级根本没测过（rubric 缺这条锚点）。
            # 正确答案是未测得、上限 L1：没测过的东西不能替学员认领，
            # 也不能反过来判他 L0。
            "dims": {"工具操作": "L2", "质量验证": "L0", "需求表达": "未测得", "自动化编排": "未测得"},
            "s1": "pass", "overall": "L0",
        },
    },
]


def main():
    bad = 0
    for c in CASES:
        got = grade.aggregate(c["verdicts"])
        print(f"\n{c['name']}")
        for dim, want in c["expect"]["dims"].items():
            g = got["dimensions"][dim]["level"]
            ok = g == want
            bad += not ok
            print(f"  [{' ok ' if ok else 'FAIL'}] {dim:<8} 期望={want:<6} 实得={g}")
        for key, label in (("s1", "S1"), ("overall", "总等级"), ("capped_by_s1", "S1 封顶")):
            if key not in c["expect"]:
                continue
            want = c["expect"][key]
            g = got["s1"] if key == "s1" else got.get(
                "overall" if key == "overall" else "capped_by_s1")
            ok = g == want
            bad += not ok
            print(f"  [{' ok ' if ok else 'FAIL'}] {label:<8} 期望={want}  实得={g}")
    print("\n" + ("聚合规则全部通过" if not bad else f"{bad} 条不符"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
