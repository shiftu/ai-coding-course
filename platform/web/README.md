# web 前端

学员看到的 5 个页面。纯标准库，服务端出完整 HTML —— 没有构建步骤、没有
node_modules、没有框架版本要跟。100 人/年的内部平台，多一条工具链就多一样
会腐烂的东西。

```
sitepath.py   把 control/ 和 curriculum/ 挂进 sys.path（路径只在这里定义一次）
data.py       只读数据层：档案 / 证据 / 批改 / 课程内容
session.py    HMAC 签名 cookie（没有会话表）
larksso.py    飞书 OAuth
ttyproxy.py   ttyd 反代（HTTP + WebSocket，字节对拷）
render.py     HTML + SVG 雷达图 + 极简 markdown
pages.py      5 个页面的正文
serve.py      路由 + HTTP server + CSS
test_web.py   离线端到端测试
live_probe.py 对着真 ttyd 验反代（要 docker）
```

## 跑起来

```bash
# 正式：必须配飞书应用
export MICROCLASS_LARK_APP_ID=cli_xxx
export MICROCLASS_LARK_APP_SECRET=yyy
export MICROCLASS_WEB_BASE=https://microclass.example.com   # 回调地址用它拼
python3 serve.py --host 127.0.0.1 --port 7900

# 本地开发：没有飞书，用「填学员 ID 直接进」
python3 serve.py --dev-login

# 刚 clone、一个学员都没有时：顺手造一份只有档案的开发学员（没有容器、没有 key，可重复）
python3 serve.py --dev-login --dev-student stu-dev
```

对外用 nginx/Caddy 终止 TLS 再反代到这里，并把 `X-Forwarded-Proto` 传进来
（cookie 的 `Secure` 标志靠它）。**这个服务自己不做 TLS。**

### 开发登录的三道闸

`--dev-login` 等于没有认证。所以：必须显式打开、必须 `--host 127.0.0.1`、
必须**没有**配飞书应用（配了就说明是正式环境）。三条缺一不可，少一条直接退出。

开发登录**只认档案里有的学员**，这一条不放开 —— 否则任何人填个 ID 就能造出学员。
空仓库想看页面，用 `--dev-student <ID>` 造档案：它只写一份 JSON（`dev_seed: true`），
`sandctl list` 里显示为「无(开发)」，`sandctl destroy <ID>` 删掉。要真沙盒还是走 `sandctl create`。

## 五个页面

| 路径 | 页面 | 数据来自 |
|---|---|---|
| `/login` | 登录 | 飞书 SSO |
| `/assess` | 测评（内嵌 web 终端） | `sandctl` 档案 + 容器状态 |
| `/track` | 我的轨道 | `curriculum/tracks/*.yaml` + 档案里的模块记录 |
| `/showcase` | 案例 | `curriculum/showcase/` 里脱敏后的精选录屏 + 讲解 |
| `/me` | 能力雷达 | 最近一批**判过分的** `grade.json` |
| `/evidence` | 我的证据 | `manifest.json` + `grade.json` 的证据链 + 录屏（网页内回放） |

`/` 跳 `/track`。

### 录屏在网页里放

asciinema-player 打进了仓库（`static/asciinema-player/`，Apache-2.0，版本号在文件名里），
同源加载。CSP 只为它开了一个口：`script-src 'self' 'wasm-unsafe-eval'` ——
播放器的终端模拟是 Rust 编成 WebAssembly 的。**不开 unsafe-inline**，所以初始化
脚本单独放在 `static/cast-player.js`，页面里只留 `<div data-cast="…">` 占位。
升级播放器 = 换两个文件 + 改 `render.PLAYER_VERSION` 一处。

同一个录屏 URL 两种用法：播放器 fetch 它（`Content-Disposition: inline`），
链接加 `?dl=1` 才当附件下载。

### 案例（showcase）是唯一一条从录屏到"所有人可见"的路

`/showcase/<模块>/<目录>` 只读仓库里的 `curriculum/showcase/`，学员证据目录里的东西
这条路一个字节都碰不到。进那个目录的文件都经过 `sandctl showcase` 脱敏 + git 审核
（见 `platform/control/README.md`）。路径段先过字符集、再 resolve 确认在目录内，
只放出 `session.cast`，`case.yaml` / `notes.md` 走页面渲染不直接下发。
毕业生也能看案例 —— 案例是课程内容，不是采集。

## 几个不是随手做的决定

### 1. 雷达图上「未测得」是断口，不是零

四维里没测到的那一维**不画顶点**，多边形就在那里断开，轴画成虚线，端点是一个
空心方块。把未测得画成 0 会让人以为自己在那一维得了最低分，而事实是那一维
这次根本没测。这和 `rubric.md` 的立场是同一件事：**未测得 ≠ 通过 ≠ 不及格**。

L3/L4 两圈用另一种样式画出来并标注「走作品制」—— 否则「最外两圈永远够不着」
看起来像学员的问题。

变异测试确认过这一条是活的：把「未测得」当 L0 画，三条断言立刻变红。

### 2. 进度只认记录，不做推断

`/track` 上的进度只读档案里的 `modules`，由 `sandctl module` 写。
**没有记录就是未开始。** 不从容器活动、不从证据、不从任何别的地方推断。
推断出来的进度会让人以为自己学过了。

### 3. 登录不能开通账号

SSO 成功但没有对应学员档案时，页面把 open_id 显示出来让人去找管理员，
**不自动建档案、更不自动建容器**。否则任何一个能走完 SSO 的人都能把宿主机的
卷和端口耗光。开通走 `sandctl create` + `sandctl bind`。

### 4. 终端反代：容器身份不进 URL

ttyd 挂在固定前缀 `/t` 下（`sandbox.TTYD_BASE_PATH`，容器侧和前端共用同一个
常量）。学员身份从 session cookie 取，**不从 URL 取** —— URL 里没有可篡改的东西。

反代不解析上游响应，只做字节对拷，所以 HTTP 和 WebSocket 升级走同一条路径。
ttyd 的 basic auth 口令由前端替学员填上，**浏览器永远拿不到**；同时前端的
会话 cookie 也不会转发给容器。

> **为什么必须有 base-path**：ttyd 的页面引用的是绝对路径（`/ws`、`/token`）。
> 挂在根上时，反代到 `/term/xxx/` 会让这些资源 404。

### 5. 改前缀是破坏性的，所以档案里记着它

`sandctl create` 把 `ttyd_base_path` 记进学员档案。改过 `TTYD_BASE_PATH` 之后，
老容器仍挂在老前缀上，代过去只会 404 —— 前端检查这个字段对不对得上，
对不上就直说「这个容器要重建」，而不是给学员一块白屏。

**已知影响**：`ttyd_base_path` 这个字段是这次才加的，在此之前建的容器
（档案里这个字段是 `None`）都需要 `sandctl destroy <学员> --keep-volume`
再 `sandctl create` 重建一次。卷里的东西不会丢。

## 隐私（设计文档 §8）

- SSO **只取 open_id**，不取姓名、邮箱、部门。
- 毕业之后：`/assess` 不再提供终端，`/t/` 直接 403，沙盒也起不来。
  `/evidence` 仍然给看 —— 那是学员自己的东西，只是不会再增加。
- 日志只记方法、路径、状态码。**不记 cookie、不记 query**（OAuth 的 `code`
  在 query 里）。

## 测试

```bash
python3 test_web.py     # 离线：起服务器、用 HTTP 打进去，36 条断言
python3 live_probe.py   # 联机：建一个真容器，验反代能拿到 200 和 101
```

`test_web.py` 唯一 mock 的是 `sandbox.container_state`（它要 docker，而登录闸、
越权、路径穿越、雷达图怎么画和 docker 没关系）。

### 做过变异测试

绿色的测试骗过人，所以逐条把保护拆掉，确认测试真的会红：

| 拆掉什么 | 测试反应 |
|---|---|
| 终端反代里的毕业检查 | 红 1 条 |
| 「未测得」当 L0 画 | 红 3 条 |
| 会话签名校验 | 红 2 条 |
| 开发入口的开关 | 红 1 条 |
| 跨学员取录屏的白名单 | 红 1 条 |
| 录屏文件名的分隔符检查 | **仍然全绿** |

最后一条是真实结论，不是遗漏：真正拦住越权的是白名单（只在这名学员自己的
证据目录里逐个比对文件名），文件名检查是第二层。留着它是纵深防御，
**但别以为有测试在盯着它**。

## 还没做的

- **飞书 SSO 没有对着真的飞书应用跑过**（手上没有 app_id/secret）。
  代码路径按官方 OAuth 2.0 授权码流程写的，`state` 走 cookie 双向校验防 CSRF，
  但「真的能登进去」这句话现在还没有证据支撑 —— 第一次配好应用之后必须实测。
- 没有管理员视图。按设计文档 §1 的取舍，管理台已砍，抽查走 Gitea + 飞书。
  挑案例进 showcase 也是命令行（`sandctl showcase`），web 没有入口，这是有意的。
