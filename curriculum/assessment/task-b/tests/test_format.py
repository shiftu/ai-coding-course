from collections import Counter

from oncall_digest.format import render_digest


def test_render_digest_includes_header_and_totals():
    out = render_digest(
        "2026-08-17",
        7,
        Counter({"zhangwei": 3, "liyang": 2}),
        {"zhangwei": 45.0},
        "02",
        Counter({"P1": 2}),
    )
    assert "# 值班日报 · 2026-08-17" in out
    assert "- 告警总数：7" in out
    assert "- 最忙时段：02 点" in out
    assert "- zhangwei × 3，平均 45 分钟" in out
    assert "- liyang × 2" in out
    assert "- P1 × 2" in out


def test_render_digest_handles_quiet_day():
    out = render_digest("2026-08-20", 0, Counter(), {}, None, Counter())
    assert "- 最忙时段：（今日无告警）" in out
    assert out.count("- （今日无告警）") == 2
