from collections import Counter

from weekly_report.render import render


def test_render_includes_title_and_total():
    out = render("研发一组", 15, ["Alice", "Bob"], Counter({"发布": 3}))
    assert "# 研发一组 周报" in out
    assert "消息总数：15" in out
    assert "- #发布 × 3" in out


def test_render_handles_empty_topics():
    out = render("研发一组", 0, [], Counter())
    assert "（本周无标记话题）" in out
