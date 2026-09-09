from oncall_digest.load import load_alerts


def test_load_alerts_returns_every_record():
    assert len(load_alerts()) == 19


def test_load_alerts_filters_by_day():
    alerts = load_alerts("2026-08-17")
    assert len(alerts) == 7
    assert all(a["fired_at"].startswith("2026-08-17") for a in alerts)
