# showcase · 精选案例

设计：`docs/design/cast-replay-showcase.md`。入库命令：`platform/control/sandctl showcase`。

这里的每一段录屏都来自真实的测评/课程沙盒 —— 老师录的和学员录的一视同仁，
**好例和反例都收**。进来的文件都经过脱敏，并由挑选人从头看过、写了讲解。
web 前端的「案例」页只读这个目录，学员证据目录里的东西不会出现在这里。

## 结构

```
showcase/<模块 id>/<good|bad>-<slug>/
├── case.yaml       五个字段（下面）
├── session.cast    脱敏后的 asciicast v2
└── notes.md        讲解，必填 —— 回放只显示做了什么，为什么要人写
```

```yaml
module: m3-hermes           # 挂在哪个模块，必须在某条轨道里
verdict: good               # good 好例 / bad 反例，目录名以它开头
title: 新会话验证记忆生效
source: teacher             # teacher | student，不写具体是谁
picked_by: panda            # 谁挑的，追溯用
```

## 入库流程（人做的部分不能省）

1. `sandctl showcase <学员> <录屏> --module … --as … --title … --slug … --by …`
   —— 脱敏副本落盘，原文件不动，**不 commit**。
2. **从头看一遍 `session.cast`。** 脱敏器只认已知模式，一个密钥被终端拆成两段输出
   它就看不见。看到漏网的直接改 `.cast` 文本。
3. 写 `notes.md`，删掉模板里那段复核提示（留着 `validate.py` 会拦）。
4. `python3 validate.py` 过了再 `git add`、提 PR。PR 就是审核。

## 校验

`validate.py` 对每个案例检查：`case.yaml` 五个字段齐全且取值合法、目录在对应模块下、
目录名以 verdict 开头、`session.cast` 是 width > 0 的 v2、`notes.md` 非空且不含模板提示。
规则只写在 `platform/control/showcase.py` 一处，入库时和校验时用同一份。
