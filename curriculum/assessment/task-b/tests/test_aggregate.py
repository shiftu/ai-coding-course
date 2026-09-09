from oncall_digest.aggregate import (ack_latency, busiest_hour,
                                     count_by_assignee, resolve_latency,
                                     severity_breakdown)
from oncall_digest.load import load_alerts

ALERTS = load_alerts()


def test_count_by_assignee():
    counts = count_by_assignee(ALERTS)
    assert counts["zhangwei"] == 5
    assert counts["wangqi"] == 3


def test_busiest_hour_returns_hour_not_date():
    assert busiest_hour(ALERTS) == "02"


def test_ack_latency_handles_alerts_across_midnight():
    # liyang 手上有一条 23:58 触发、次日 00:04 认领的告警
    assert ack_latency(ALERTS)["liyang"] == 14.5


def test_resolve_latency_skips_open_alerts():
    # chenhao 的 4 条里有 1 条还没关闭，只按已关闭的 3 条算
    assert round(resolve_latency(ALERTS)["chenhao"], 2) == 67.33


def test_severity_breakdown_covers_all_alerts():
    assert sum(severity_breakdown(ALERTS).values()) == len(ALERTS)
