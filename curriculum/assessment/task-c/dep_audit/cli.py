"""命令行入口：python -m dep_audit.cli --project <名字>"""
import argparse

from .classify import classify_all
from .report import render_markdown
from .scan import scan_dependencies


def main():
    parser = argparse.ArgumentParser(description="扫描依赖清单，输出许可证风险报告")
    parser.add_argument("--project", default="风控后台", help="项目名，用于报告标题")
    parser.add_argument("--manifest", default=None, help="依赖清单路径，默认读 sample_data/")
    args = parser.parse_args()

    deps = scan_dependencies(args.manifest)
    print(render_markdown(args.project, classify_all(deps)))


if __name__ == "__main__":
    main()
