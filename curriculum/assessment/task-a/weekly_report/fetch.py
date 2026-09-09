"""从飞书群拉取消息。测试环境下走本地样例数据，不打网络。"""
import json
import os
import pathlib

SAMPLE = pathlib.Path(__file__).parent.parent / "sample_data" / "messages.json"


def fetch_messages(chat_id, since=None):
    """返回消息列表。

    线上走 lark-cli；本地/测试环境读 sample_data。
    """
    if os.environ.get("WEEKLY_REPORT_OFFLINE", "1") == "1":
        return json.loads(SAMPLE.read_text(encoding="utf-8"))
    raise NotImplementedError("在线拉取尚未接入，见 Issue #4")
