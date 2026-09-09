"""把统计结果渲染成 Markdown 周报。"""


def render(chat_name, total, top, topics):
    lines = [
        f"# {chat_name} 周报",
        "",
        f"- 消息总数：{total}",
        f"- 活跃贡献者：{', '.join(top) if top else '（无）'}",
        "",
        "## 热门话题",
    ]
    if topics:
        for name, n in topics.most_common(5):
            lines.append(f"- #{name} × {n}")
    else:
        lines.append("- （本周无标记话题）")
    return "\n".join(lines) + "\n"
