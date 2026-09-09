"""读取告警记录。

线上从 SNS 订阅落库的告警表里查；本地和测试环境读 sample_data。
"""
import json
import os
import pathlib

SAMPLE = pathlib.Path(__file__).parent.parent / "sample_data" / "alerts.json"


def load_alerts(day=None):
    """返回告警记录列表，`day` 形如 "2026-08-17"。

    离线开关默认打开：值班同学在自己机器上出一份日报，不该先去申一套 AWS 凭据。
    """
    if os.environ.get("ONCALL_DIGEST_OFFLINE", "1") == "1":
        alerts = json.loads(SAMPLE.read_text(encoding="utf-8"))
        if day is None:
            return alerts
        return [a for a in alerts if a["fired_at"].startswith(day)]
    raise NotImplementedError("在线查询尚未接入，见 Issue #9")
