#!/usr/bin/env bash
# 沙盒镜像冒烟。版本/路径类断言不在这里重复写 —— 它们在镜像内的
# microclass-selfcheck 里，构建期和运行期共用同一份，避免两处漂移。
# 这里只补 selfcheck 做不到的：录屏产出、默认 CMD、以及端到端跑一次真模型。
#
# 端到端那项要 key：
#   MICROCLASS_SMOKE_KEY=$(cat ~/.config/microclass/smoke-key) ./smoke.sh
set -uo pipefail
cd "$(dirname "$0")"
IMG="${MICROCLASS_IMAGE:-microclass/sandbox:current}"
GW="${MICROCLASS_GATEWAY:-http://192.168.5.2:7421}"
pass=0; fail=0
ok()  { echo "  ok   $1"; pass=$((pass+1)); }
bad() { echo "  FAIL $1"; echo "       $2"; fail=$((fail+1)); }

echo "镜像 $IMG"
echo
echo "[1] 镜像自检（登录 shell 里跑，学员看到的就是这个 shell）"
if out=$(docker run --rm --entrypoint /bin/bash "$IMG" -lc microclass-selfcheck 2>&1); then
  echo "$out" | sed 's/^/  /'; pass=$((pass+1))
else
  echo "$out" | sed 's/^/  /'; fail=$((fail+1))
fi

echo
echo "[2] 镜像身份：戳烙进去了，而且和工作树对得上"
# 为什么要查这个：档案里记的环境全靠这个戳和 image id。镜像要是没戳
# （比如有人绕过 build.sh 直接 docker build），档案就退回到"只记一个会撒谎的 tag"，
# 而这正是当初 stu-jt / stu-p 的环境无从回溯的原因。
stamp=$(docker image inspect "$IMG" --format '{{index .Config.Labels "org.microclass.image-stamp"}}' 2>/dev/null)
want=$(./stamp.sh)
if [ -z "$stamp" ] || [ "$stamp" = "unknown" ]; then
  bad "镜像身份" "镜像没有 org.microclass.image-stamp —— 它不是 ./build.sh 构建的。
       直接 docker build 不会传 IMAGE_STAMP，出来的镜像说不清自己是哪份输入产出的。"
elif [ "$stamp" != "$want" ] && [ "$IMG" = "microclass/sandbox:current" ]; then
  # 只对 :current 判红：显式指定老镜像来跑冒烟是正当用法，不该报错。
  bad "镜像身份" "镜像戳 $stamp ≠ 工作树 $want —— rootfs/Dockerfile/versions.lock 改过但没重建。
       现在交付出去的容器和仓库里的代码不是一回事。跑 ./build.sh"
else
  ok "构建戳 $stamp"
fi

echo
echo "[3] 证据目录可写"
for d in /evidence /workspace; do
  got=$(docker run --rm --entrypoint /bin/bash "$IMG" -lc "touch $d/.probe && echo writable" 2>&1)
  case "$got" in *writable*) ok "$d" ;; *) bad "$d" "$got" ;; esac
done

echo
echo "[4] 录屏真的产出 asciinema v2 .cast"
got=$(docker run --rm --entrypoint /bin/bash "$IMG" -lc \
  'asciinema rec -q --command "echo hello-cast" /evidence/s.cast >/dev/null 2>&1; head -c 60 /evidence/s.cast' 2>&1)
case "$got" in *'"version": 2'*|*'"version":2'*) ok "cast 头是 v2" ;;
  *) bad "asciinema 录制" "cast 头不像 v2：$got" ;; esac

echo
echo "[5] 默认 CMD 是登录 bash，且不拉起基底的 s6 监督树"
# 不能给参数：参数会把 CMD 整个替换掉。喂 stdin 才是在测默认 CMD。
got=$(echo 'echo alive; command -v python3' | docker run --rm -i "$IMG" 2>&1)
case "$got" in *alive*) ok "默认 CMD 起得来" ;; *) bad "默认 CMD" "$got" ;; esac
case "$got" in *'/opt/hermes/.venv/bin/python3'*) ok "默认 CMD 里 python3 也指向 venv" ;;
  *) bad "默认 CMD 的 PATH" "python3 没指向 venv：$got" ;; esac

echo
echo "[6] 端到端：claude-code 经内部网关跑 Bash，且不被权限拦下"
if [ -z "${MICROCLASS_SMOKE_KEY:-}" ]; then
  echo "  skip 没给 MICROCLASS_SMOKE_KEY（这是唯一花钱的一项）"
else
  got=$(docker run --rm --entrypoint /bin/bash \
      -e ANTHROPIC_BASE_URL="$GW" \
      -e ANTHROPIC_AUTH_TOKEN="$MICROCLASS_SMOKE_KEY" \
      -e ANTHROPIC_MODEL=charaboard/claude-sonnet-5 \
      -e ANTHROPIC_SMALL_FAST_MODEL=charaboard/claude-sonnet-5 \
      "$IMG" -lc 'cd /workspace && claude -p "Use the Bash tool to run: python3 -c \"print(6*7)\" and tell me the number." --output-format json 2>&1')
  read -r n_deny result <<<"$(printf '%s' "$got" | python3 -c '
import sys, json
raw = sys.stdin.read(); i = raw.find("{")
try:
    d = json.loads(raw[i:])
    print(len(d.get("permission_denials", [])), (d.get("result") or "").replace("\n"," ")[:70])
except Exception:
    print("parse-fail", raw[:150].replace("\n"," "))')"
  if [ "$n_deny" = "0" ]; then
    case "$result" in *42*) ok "0 次权限拦截，且算出 42 —— 证据链干净" ;;
      *) ok "0 次权限拦截（返回：$result）" ;; esac
  else
    bad "端到端" "权限拦截 $n_deny 次 / $result"
  fi
fi

echo
echo "───────────────────────────"
echo "通过 ${pass}，失败 ${fail}"
[ "$fail" = 0 ] || exit 1
