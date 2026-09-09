"""把统计结果渲染成 Markdown 日报。"""


def render_digest(day, total, calls, latency, busiest, severities):
    lines = [
        f"# 值班日报 · {day}",
        "",
        f"- 告警总数：{total}",
        f"- 最忙时段：{busiest} 点" if busiest else "- 最忙时段：（今日无告警）",
        "",
        "## 呼叫次数",
    ]
    if calls:
        for name, n in calls.most_common():
            # 没有闭环记录的人不显示耗时，写"0 分钟"会被误读成响应神速
            minutes = latency.get(name)
            tail = f"，平均 {minutes:.0f} 分钟" if minutes is not None else ""
            lines.append(f"- {name} × {n}{tail}")
    else:
        lines.append("- （今日无告警）")

    lines += ["", "## 严重级别"]
    if severities:
        for level, n in sorted(severities.items()):
            lines.append(f"- {level} × {n}")
    else:
        lines.append("- （今日无告警）")
    return "\n".join(lines) + "\n"
