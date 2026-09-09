# AI 微课堂 · 学员沙盒镜像（linux/arm64）
#
# 基底是 hermes 官方镜像 —— 它已经带了 node / uv / git / ripgrep / ffmpeg，
# 叠上四件工具后单镜像约 5GB。不拆多层：spike 实测共存无冲突（spike-feasibility §10）。
#
# 全部版本从 versions.lock 传入，不在这里写死。用 build.sh 构建。
# 需要 BuildKit（基底的 hermes Dockerfile 用了 COPY --chmod）。

ARG HERMES_BASE
FROM ${HERMES_BASE}

ARG CLAUDE_CODE_VERSION
ARG CODEX_VERSION
ARG LARK_CLI_VERSION
ARG TTYD_VERSION
ARG ASCIINEMA_VERSION
ARG PYTEST_VERSION
ARG GLOW_VERSION

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# ── 系统件：录屏、web 终端、速查卡要用的 glow（渲染），less（兜底）───
RUN apt-get -o Acquire::Retries=3 update \
 && apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
      asciinema less fd-find ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && ln -sf "$(command -v fdfind)" /usr/local/bin/fd \
 && curl -fsSL --retry 5 -o /usr/local/bin/ttyd \
      "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.aarch64" \
 && chmod 0755 /usr/local/bin/ttyd \
 && curl -fsSL --retry 5 "https://github.com/charmbracelet/glow/releases/download/v${GLOW_VERSION}/glow_${GLOW_VERSION}_Linux_arm64.tar.gz" \
      | tar xz -C /tmp "glow_${GLOW_VERSION}_Linux_arm64/glow" \
 && mv "/tmp/glow_${GLOW_VERSION}_Linux_arm64/glow" /usr/local/bin/glow \
 && rm -rf "/tmp/glow_${GLOW_VERSION}_Linux_arm64" \
 && chmod 0755 /usr/local/bin/glow

# ── 四件工具（版本钉死）──────────────────────────────────────────────
RUN npm i -g --no-audit --no-fund \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
      "@openai/codex@${CODEX_VERSION}" \
      "@larksuite/cli@${LARK_CLI_VERSION}" \
 && npm cache clean --force

# ── 沙盒镜像要求 4：hermes 必须在 PATH 上 ────────────────────────────
# 二进制在 /opt/hermes/bin/hermes，但学员敲 `hermes` 时 command -v 找不到。
RUN ln -sf /opt/hermes/bin/hermes /usr/local/bin/hermes \
 && command -v hermes >/dev/null || { echo "hermes 不在 PATH 上"; exit 1; }

# ── 沙盒镜像要求 2+3：练习依赖，且装进学员真正调用的那个 python ──────
# 基底把 /opt/hermes/.venv/bin 放在 PATH 最前，所以 `python3` 解析到它。
# 装进 /usr/bin/python3 的包，学员敲 python3 -m pytest 是看不见的。
RUN uv pip install --no-cache-dir --python /opt/hermes/.venv/bin/python3 \
      "pytest==${PYTEST_VERSION}"

# ── 沙盒镜像要求 1：claude-code 不拦 Bash ────────────────────────────
# 权限弹窗会在会话记录里留下 is_error:true + "requires approval"，
# 让"从没验证过"和"验证被拦下"无法区分 —— 直接毒化整条证据链。
# 隔离边界是容器本身，不是权限弹窗（设计文档 §6）。
COPY rootfs/etc/claude-code/ /etc/claude-code/

# ── 沙盒镜像要求 5：git 必须认预置进来的仓库 ────────────────────────
# 见 rootfs/etc/gitconfig 里的说明 —— 不加这条，证据源 ② 会整条哑掉。
COPY rootfs/etc/gitconfig /etc/gitconfig

# ── 速查卡、登录初始化、录屏包装 ─────────────────────────────────────
COPY rootfs/opt/microclass/ /opt/microclass/
COPY rootfs/etc/profile.d/ /etc/profile.d/
# --chmod 让"可执行"成为 COPY 的一部分，而不是后面一条独立的 chmod。
# 这里踩过两次：先是写死名单（漏了 microclass-doctor，Permission denied），
# 改成 chmod microclass-* 之后又漏了 card —— 它不叫 microclass-*。
# 任何"记得同步一下模式位"的方案迟早会漏，所以让它没有可漏的地方：
# 凡是进了这个目录的，就是 0755。
COPY --chmod=0755 rootfs/usr/local/bin/ /usr/local/bin/

# 证据落盘点，harvest 从这里取
RUN mkdir -p /evidence /workspace

# ── 自检：镜像里的实际版本必须和 versions.lock 一致 ─────────────────
# asciinema 走 apt，装到什么版本不由我们说了算；不断言的话 versions.lock 就是
# 一句谎话，而哨兵 cron 正是拿它当真源做 diff。
# 必须用登录 shell —— /etc/profile 会重置 PATH，非登录 shell 的绿灯是假绿。
RUN CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION}" \
    CODEX_VERSION="${CODEX_VERSION}" \
    LARK_CLI_VERSION="${LARK_CLI_VERSION}" \
    TTYD_VERSION="${TTYD_VERSION}" \
    ASCIINEMA_VERSION="${ASCIINEMA_VERSION}" \
    PYTEST_VERSION="${PYTEST_VERSION}" \
    GLOW_VERSION="${GLOW_VERSION}" \
    bash -lc microclass-selfcheck

# 自检要用的期望值随镜像走，sandctl 交付容器前可以随时复跑
ENV CLAUDE_CODE_VERSION=${CLAUDE_CODE_VERSION} \
    CODEX_VERSION=${CODEX_VERSION} \
    LARK_CLI_VERSION=${LARK_CLI_VERSION} \
    TTYD_VERSION=${TTYD_VERSION} \
    ASCIINEMA_VERSION=${ASCIINEMA_VERSION} \
    PYTEST_VERSION=${PYTEST_VERSION} \
    GLOW_VERSION=${GLOW_VERSION}

# ── 镜像自报身份：构建戳随镜像走 ───────────────────────────────────────
# 戳 = shasum(versions.lock + Dockerfile + 整个 rootfs)，由 build.sh 传进来。
# 为什么要烙进镜像而不是只当 tag：tag 是宿主机上一个可以随手改掉的标签，
# `docker tag` 一句话就能让它指向别的镜像，学员档案里那行 image 从此撒谎。
# 烙进 LABEL + ENV 之后，镜像走到哪都能自己说清楚"我是哪一版构建输入产出的"——
# 连 tag 被删掉、只剩一个还在跑的容器时也答得出来。
# 故意放在最后：改戳不该让前面那些几个 G 的层重建。
ARG IMAGE_STAMP=unknown
LABEL org.microclass.image-stamp="${IMAGE_STAMP}"

ENV MICROCLASS_IMAGE_STAMP=${IMAGE_STAMP} \
    MICROCLASS_IMAGE_BUILT=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

WORKDIR /workspace

# 基底的 ENTRYPOINT 会拉起 s6 监督树（需要 root 且我们并不需要它）——
# 学员沙盒里 hermes 是当 CLI 用的，不是当 daemon。这里覆盖掉。
ENTRYPOINT []
CMD ["/bin/bash", "-l"]
