"""让 web/ 能 import 到 control/ 和 curriculum/ 的模块。

单独一个文件而不是每个模块各写一遍 sys.path —— 路径只有一处定义，
将来目录挪了只改这里。
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

for p in (ROOT / "platform" / "control", ROOT / "curriculum"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
