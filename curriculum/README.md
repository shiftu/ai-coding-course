# curriculum · 课程内容仓库

对应设计文档 `platform-design-v1.1.md` §5（课程组织）与 §7（内容保鲜）。

## 结构

```
slices/       56 条切片，路径即分类：<维度>/<slug>.md
tracks/       3 条轨道，每条是一份模块清单
rubric/       测评判定表 + 打分器 + 判定器（见 rubric/rubric.md）
assessment/   测评任务仓库（见 assessment/README.md）
validate.py   切片/轨道一致性校验 + 机验执行
```

## 核心转换

**课程按天组织，切片按维度组织。** 原来的 10 课是时间线（D1…D10），
切片是能力维度（工具操作 / 需求表达 / 质量验证 / 自动化编排 / safety-gate）。
轨道文件再把切片排回可读的学习顺序。

这样做的理由：测评产出的是**四维向量**，要按短板推荐内容，就必须能按维度检索切片。
按课号组织做不到这件事。

## 切片 schema（5 个字段，来自 §5.1）

```yaml
id: quality/verify-before-done   # 必须与文件路径一致
dimension: 质量验证               # 四维之一，或 safety-gate
level_edge: L1->L2               # 或 S1/S2/S3（safety-gate 专用）
type: exercise                   # demo | exercise | pitfall | quiz
env: container                   # container | own-mac
verify:                          # 可选
  - cmd: "pytest -q"
    expect_exit: 0
```

### verify 的语义（容易搞错，写清楚）

机验回答的是 **「这条切片教的命令，在当前工具版本下还存在吗」**，
**不是**「学员做没做作业」。哨兵 cron 每周在干净环境里跑一遍，跑不通 = 内容可能过时 → 开 Issue。

由此有两条硬规则：

1. **必须按 `env` 过滤。** `own-mac` 切片的机验依赖学员本机（回环网关、个人 key），
   在容器里跑必然失败。假警报会让哨兵 Issue 迅速失去可信度。
   ```bash
   python3 validate.py --verify container    # 沙盒里跑
   python3 validate.py --verify own-mac      # 本机跑
   ```
2. **机验不能依赖个人凭据或特定工作目录。** 反例两个，都踩过：
   - `curl ... -H "Authorization: Bearer $LLM_GW_KEY"` —— 哨兵没有学员的 key，
     改成探无需鉴权的 `/healthz`；
   - `grep -r 'sk-…' .` 扫密钥 —— 课程仓库里本来就存着测评任务**故意预埋的假密钥**，
     这条永远会红。该切片已改为不设机验。

## 轨道

| 轨道 | 进入条件 | 模块 / 切片 |
|---|---|---|
| A · 零基础 | 快筛未过，或测评多维 L0 | 11 / 56 |
| B · 有基础 | 测评多维 L1–L2 | 9 / 46 |
| C · 资深 | 导师背书直升 | 7 / 33 |

B 跳过 CLI 结对（m2）与需求表达（m4）两个通用入门模块。
**质量守门（m5）不跳** —— 短板决定制下，通用能力强不等于验证习惯好。

C 只上公司特有模块 + 毕业项目，通用能力由背书导师负责。

每个模块带 `exempt_test`（免修考）——轨道内的细粒度个性化由它完成，
所以不需要装配算法（§5）。

## 沙盒镜像的硬性要求

这四条全部是实测踩出来的，写在这里防止重犯：

1. **claude-code 必须配成不拦 Bash。** 否则复合命令（如 `pytest -q | tail -30`）会被权限
   系统拦下，且会话记录里留下 `is_error: true` —— 学员会被批改成"从未验证过"。
   详见 `rubric/rubric.md` §1。
2. **必须预装练习任务的依赖**（本课程是 `pytest`）。
3. **依赖要装在学员实际会用到的那个 python 下。** hermes 镜像把 `/opt/hermes/.venv/bin`
   放在 PATH 最前，`pip3 install` 装进 `/usr/bin/python3` 的包，学员敲 `python3 -m pytest`
   是找不到的。用 `uv pip install --python /opt/hermes/.venv/bin/python3`。
4. **`hermes` 必须在 PATH 上。** 镜像里二进制在 `/opt/hermes/bin/hermes`，
   但容器里 `command -v hermes` 找不到 —— 学员敲 `hermes` 会 not found。

## 自检

```bash
python3 validate.py                      # 结构一致性（离线）
python3 validate.py --verify container   # 沙盒环境机验
python3 validate.py --verify own-mac     # 本机环境机验
```

`validate.py` 检查：字段完整性、id 与路径一致、枚举值合法、
轨道引用的切片存在、同轨道内无重复、**无孤儿切片**（没有任何轨道引用的切片 = 死内容）。

它只接受一个明确的 YAML 子集，超出就报错而不是静默误读 —— 这个仓库没有 pyyaml 依赖。

## 现状（2026-08-20）

- 结构校验：通过，56 条切片全部被引用，0 孤儿
- 机验：container 4/4、own-mac 4/4
- 未做：任务 B/C 变体、速查卡内容、哨兵 cron 本体（§7）
