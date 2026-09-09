"""把原始告警记录汇总成日报需要的统计量。"""
from collections import Counter, defaultdict
from datetime import datetime


def _minutes_between(start, end):
    """两个 ISO 时间戳之间相差多少分钟。

    这里走 datetime 而不是直接拿时间部分相减，是因为告警经常跨零点——
    23:58 触发、次日 00:04 认领，只看时分会算出负数。
    """
    delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    return delta.total_seconds() / 60


def _average_by_assignee(alerts, end_field):
    """按人求平均耗时。end_field 缺失的记录直接跳过，未闭环的告警不该拉低平均值。"""
    buckets = defaultdict(list)
    for a in alerts:
        if not a.get(end_field):
            continue
        buckets[a["assignee"]].append(_minutes_between(a["fired_at"], a[end_field]))
    return {name: sum(v) / len(v) for name, v in buckets.items()}


def count_by_assignee(alerts):
    """每个人被呼叫了多少次。"""
    return Counter(a["assignee"] for a in alerts)


def ack_latency(alerts):
    """每个人从告警触发到认领的平均分钟数。"""
    return _average_by_assignee(alerts, "acked_at")


def resolve_latency(alerts):
    """每个人从告警触发到关闭的平均分钟数。"""
    return _average_by_assignee(alerts, "resolved_at")


def busiest_hour(alerts):
    """哪个小时告警最多。"""
    hours = Counter(a["fired_at"].split("T")[0] for a in alerts)
    return hours.most_common(1)[0][0] if hours else None


def severity_breakdown(alerts):
    """告警按严重级别的分布。"""
    return Counter(a["severity"] for a in alerts)
