#!/usr/bin/env bash
# 构建学员沙盒镜像。版本全部来自 versions.lock —— 不接受命令行覆盖，
# 因为"单版本策略"的意思就是环境版本只有一个来源。
set -euo pipefail
cd "$(dirname "$0")"

LOCK=versions.lock
[ -f "$LOCK" ] || { echo "找不到 $LOCK"; exit 1; }

# 需要 BuildKit：基底的 hermes Dockerfile 用了 COPY --chmod
docker buildx version >/dev/null 2>&1 || {
  echo "缺 buildx。装：brew install docker-buildx"
  echo "再把 cliPluginsExtraDirs 加进 ~/.docker/config.json"
  exit 1
}

ARGS=()
while IFS='=' read -r k v; do
  case "$k" in ''|\#*) continue ;; esac
  ARGS+=(--build-arg "$k=$v")
done < <(sed 's/[[:space:]]*$//' "$LOCK")

[ ${#ARGS[@]} -gt 0 ] || { echo "$LOCK 里一个版本都没读到"; exit 1; }

# 基底：hermes 官方镜像自己的 Dockerfile 构建产物，见 README「基底怎么来的」
BASE=$(grep '^HERMES_BASE=' "$LOCK" | cut -d= -f2-)
docker image inspect "$BASE" >/dev/null 2>&1 || {
  echo "基底镜像 $BASE 不存在。先按 README 构建 hermes 基底。"
  exit 1
}

# 输入寻址 tag。**戳覆盖 versions.lock + Dockerfile + 整个 rootfs**，
# 见 stamp.sh 开头那段说明 —— 只哈希 versions.lock 的老做法会让
# 「改一行 card，重建」产出一个内容变了、tag 却一模一样的镜像，
# 学员档案里那行 image 就此失去意义。
STAMP=$(./stamp.sh)
TAG="microclass/sandbox:$STAMP"

# 同 tag 重建前先记下它原来指着谁。输入寻址不是内容寻址：
# 同样的 lock/Dockerfile/rootfs，apt 和 npm 上游照样会漂，
# 于是同一个戳可以对应两个不同的镜像。这种情况必须说出来，
# 不能让人以为"tag 相同 = 环境相同"。
BEFORE=$(docker image inspect "$TAG" --format '{{.Id}}' 2>/dev/null || true)

echo "构建 $TAG"
DOCKER_BUILDKIT=1 docker build \
  "${ARGS[@]}" \
  --build-arg "IMAGE_STAMP=$STAMP" \
  -t "$TAG" \
  -t "microclass/sandbox:current" \
  .

AFTER=$(docker image inspect "$TAG" --format '{{.Id}}')

echo
echo "构建完成："
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' | grep '^microclass/sandbox'
echo
echo "  构建戳  $STAMP   （versions.lock + Dockerfile + rootfs 的哈希）"
echo "  镜像 id $AFTER"
echo "  —— 学员档案记的是这两个，不是 :current。回溯环境时以 image id 为准。"

if [ -n "$BEFORE" ] && [ "$BEFORE" != "$AFTER" ]; then
  echo
  echo "  注意：同一个戳 $STAMP 这次产出了**不同的镜像**。"
  echo "    原来 $BEFORE"
  echo "    现在 $AFTER"
  echo "  构建输入一个字没变，说明是上游漂了（apt/npm 拉到了新版本）。"
  echo "  拿着旧 image id 的学员档案仍然准确 —— 那个镜像还在本地，别 prune 掉。"
fi
echo
echo "跑一遍冒烟：./smoke.sh"
