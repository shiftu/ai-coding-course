#!/usr/bin/env bash
# 镜像戳 —— 把**整套构建输入**哈希成一个 12 位串，build.sh 拿它当 tag。
#
# 为什么单独抽出来：原来 build.sh 只哈希 versions.lock，于是
# 「改一行 rootfs/usr/local/bin/card，重建，得到一个内容不同但 tag 完全相同的镜像」。
# 学员档案里记着 microclass/sandbox:3ae31c01f5c7，可这个 tag 在不同时间点
# 指向过两个不一样的环境 —— 「回溯这人当时用的是哪套环境」就成了一句空话。
# 现在 versions.lock、Dockerfile、rootfs 下每个文件的内容全都算进去。
#
#   ./stamp.sh          # 打印当前工作树的戳
#
# 注意它是**输入寻址**，不是内容寻址：同样的输入不保证产出同样的镜像
# （apt/npm 上游会漂）。镜像的真身永远以 image id 那个 sha256 为准，
# 档案里两个都记（见 control/sandbox.py image_identity）。
#
# 模式位不进哈希：/usr/local/bin 那批的可执行位由 Dockerfile 的
# COPY --chmod=0755 统一钉死，跟工作树里是什么模式无关；其余都是数据文件。
# 不哈希模式位也顺带避免了 macOS/Linux 上 stat 参数不同带来的假差异。
set -euo pipefail
cd "$(dirname "$0")"

{
  shasum -a 256 versions.lock Dockerfile
  find rootfs -type f -exec shasum -a 256 {} +
} | LC_ALL=C sort | shasum -a 256 | cut -c1-12
