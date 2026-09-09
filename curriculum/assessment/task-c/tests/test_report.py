from dep_audit.report import group_by_risk, render_markdown

CLASSIFIED = [
    {
        "name": "mysql-connector-python",
        "version": "9.1.0",
        "license": "GPL-3.0",
        "direct": True,
        "risk": "high",
        "manual_review": False,
    },
    {
        "name": "requests",
        "version": "2.32.3",
        "license": "Apache-2.0",
        "direct": True,
        "risk": "low",
        "manual_review": False,
    },
    {
        "name": "certifi",
        "version": "2024.8.30",
        "license": "MPL-2.0",
        "direct": False,
        "risk": "medium",
        "manual_review": True,
    },
]


def test_group_by_risk_buckets_every_dependency():
    groups = group_by_risk(CLASSIFIED)
    assert set(groups) == {"high", "medium", "low"}
    assert groups["high"][0]["name"] == "mysql-connector-python"


def test_render_puts_high_risk_first_and_marks_scope():
    out = render_markdown("风控后台", CLASSIFIED)
    assert "- 依赖总数：3" in out
    assert "- 高风险：1" in out
    assert "- 需人工确认：1" in out
    assert out.index("## 高风险") < out.index("## 需评估") < out.index("## 低风险")
    assert "certifi 2024.8.30 — MPL-2.0（间接依赖）" in out


def test_render_handles_empty_manifest():
    out = render_markdown("风控后台", [])
    assert "- 依赖总数：0" in out
    assert "清单为空" in out
