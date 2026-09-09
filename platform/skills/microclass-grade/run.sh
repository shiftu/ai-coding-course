#!/usr/bin/env bash
# 批改一名学员：取证 → 判定 → 落盘。skill 里的步骤合成一条命令。
#
#   ./run.sh <学员> [--no-llm]
set -euo pipefail
STU="${1:?用法: ./run.sh <学员> [--no-llm]}"; shift || true
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

echo "== 取证 =="
# --stop-first：先停容器再采证。
# 采证必须在静止态做 —— agent 还在跑的时候采，会拿到半截状态。
# 实测踩过：同一名学员先后两次采证，一次判"交白卷"，两分钟后判 L2。
OUT=$(python3 "$ROOT/control/harvest.py" "$STU" --stop-first)
echo "$OUT"
DIR=$(printf '%s' "$OUT" | sed -n 's/^.*已取到 \(.*\)$/\1/p' | head -1)
[ -n "$DIR" ] || { echo "没解析出 harvest 目录"; exit 1; }

echo
echo "== 判定 =="
python3 "$ROOT/../curriculum/rubric/grade.py" "$DIR" --student "$STU" \
        --out "$DIR/grade" "$@"

python3 - "$DIR/grade/grade.json" <<'PY'
import json, sys
g = json.load(open(sys.argv[1]))
print()
print(f"  总等级 {g['overall']}   S1 {g['s1']}")
for d, v in g["dimensions"].items():
    print(f"    {d:<8} {v['level']}")
if g.get("rubric_items_missing"):
    print(f"\n  ⚠ rubric 与打分器不同步：{g['rubric_items_missing']} —— 这是代码 bug，先修再批")
PY
echo
echo "  复盘：$DIR/grade/debrief.md"
