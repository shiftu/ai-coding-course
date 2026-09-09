"""命令行入口：python -m weekly_report.cli --chat <id>"""
import argparse

from .fetch import fetch_messages
from .render import render
from .summarize import collect_topics, count_by_author, top_contributors


def main():
    parser = argparse.ArgumentParser(description="生成飞书群周报")
    parser.add_argument("--chat", default="demo-chat", help="群 ID")
    parser.add_argument("--name", default="研发一组", help="群名，用于标题")
    args = parser.parse_args()

    messages = fetch_messages(args.chat)
    counts = count_by_author(messages)
    print(render(args.name, len(messages), top_contributors(counts), collect_topics(messages)))


if __name__ == "__main__":
    main()
