"""命令行入口：python -m oncall_digest.cli --day 2026-08-17"""
import argparse

from .aggregate import (busiest_hour, count_by_assignee, resolve_latency,
                        severity_breakdown)
from .format import render_digest
from .load import load_alerts


def main():
    parser = argparse.ArgumentParser(description="生成值班日报")
    parser.add_argument("--day", default=None, help="只看某一天，格式 2026-08-17")
    args = parser.parse_args()

    alerts = load_alerts(args.day)
    print(render_digest(
        args.day or "全部记录",
        len(alerts),
        count_by_assignee(alerts),
        resolve_latency(alerts),
        busiest_hour(alerts),
        severity_breakdown(alerts),
    ))


if __name__ == "__main__":
    main()
