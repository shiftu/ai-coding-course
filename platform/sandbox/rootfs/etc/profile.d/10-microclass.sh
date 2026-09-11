# AI 微课堂沙盒 —— 登录 shell 初始化

# PATH：/etc/profile 会重置 PATH，把镜像 ENV 里"venv 优先"的顺序冲掉。
# 后果是学员在 ttyd 登录 shell 里敲 python3 拿到 /usr/bin/python3，
# 而 pytest 装在 /opt/hermes/.venv 里 —— 于是"跑个测试"直接 ModuleNotFoundError。
# 构建期的 RUN 是非登录 shell，看不到这个差异，会给出假绿。
case ":$PATH:" in
  *":/opt/hermes/.venv/bin:"*) ;;
  *) PATH="/opt/hermes/bin:/opt/hermes/.venv/bin:$PATH"; export PATH ;;
esac

# 速查卡在 /usr/local/bin/card，**故意不做成 shell 函数**：
# 函数只活在定义它的那一个 shell 里，测评模式一 exec 进录屏就没了（实测踩过）。

# 网关地址（sandctl 注入 MICROCLASS_GATEWAY；这里只做派生，不硬编码）
if [ -n "${MICROCLASS_GATEWAY:-}" ]; then
  export ANTHROPIC_BASE_URL="${MICROCLASS_GATEWAY}"
  export OPENAI_BASE_URL="${MICROCLASS_GATEWAY}/v1"
fi

# 各工具的原生配置：一处来源渲染出去（cc-switch 的思路，脚本形态）。
# 默认不覆盖已有文件，学员亲手改过的配置不会被每次登录冲掉。
# **不加 -t 0 判断**：microclass-doctor 走的是 `docker exec bash -lc`，没有 tty。
# 加了这个判断，体检就会跑在配置生成之前，报一个假的 401 —— 实测踩过。
if [ -n "${MICROCLASS_GATEWAY:-}" ]; then
  microclass-config >/dev/null 2>&1 || true
fi

# 进 shell 即开始录制：测评模式一律录（§4.3）；课程模式只在 sandctl create --record
# 注入了 MICROCLASS_RECORD=1 时录 —— 录了才有东西可挑进精选案例库。
if { [ "${MICROCLASS_MODE:-}" = "assessment" ] || [ "${MICROCLASS_RECORD:-}" = "1" ]; } \
   && [ -z "${ASCIINEMA_REC:-}" ] && [ -t 0 ]; then
  exec microclass-record
fi

if [ -t 0 ]; then
  cat <<'BANNER'

  AI 微课堂沙盒。四件工具都装好了：claude / codex / hermes / lark-cli
  AI 请求已经走公司内部网关，不需要你填任何 key。
  忘了命令怎么写就敲：card
  环境有没有毛病，敲：microclass-doctor

BANNER
fi
