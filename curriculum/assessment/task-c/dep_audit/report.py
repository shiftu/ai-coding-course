"""把分级结果渲染成 Markdown 报告。"""

# 渲染顺序按危险程度从高到低；SEVERITY 里没有的等级排在最后，避免直接 KeyError。
SEVERITY = {"high": 0, "medium": 1, "low": 2}
LABEL = {"high": "高风险", "medium": "需评估", "low": "低风险"}


def group_by_risk(classified):
    """等级 → 该等级下的依赖列表。"""
    groups = {}
    for dep in classified:
        groups.setdefault(dep["risk"], []).append(dep)
    return groups


def _ordered_levels(groups):
    return sorted(groups, key=lambda level: (SEVERITY.get(level, 99), level))


def render_markdown(project, classified):
    """渲染完整报告。"""
    groups = group_by_risk(classified)
    manual = [dep for dep in classified if dep["manual_review"]]
    lines = [
        f"# {project} 依赖许可证审计",
        "",
        f"- 依赖总数：{len(classified)}",
        f"- 高风险：{len(groups.get('high', []))}",
        f"- 需人工确认：{len(manual)}",
        "",
    ]
    if not classified:
        lines.append("清单为空，没有可审计的依赖。")
        return "\n".join(lines) + "\n"

    for level in _ordered_levels(groups):
        lines.append(f"## {LABEL.get(level, level)}")
        for dep in sorted(groups[level], key=lambda d: d["name"]):
            scope = "直接" if dep["direct"] else "间接"
            lines.append(
                f"- {dep['name']} {dep['version']} — {dep['license']}（{scope}依赖）"
            )
        lines.append("")

    lines.append("## 需人工确认")
    if manual:
        for dep in sorted(manual, key=lambda d: d["name"]):
            lines.append(f"- {dep['name']} {dep['version']} — {dep['license'] or '清单未填'}")
    else:
        lines.append("- （无）")
    return "\n".join(lines) + "\n"
