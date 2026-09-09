# dep-audit

扫描项目的依赖清单，输出一份许可证风险报告：哪些包有风险、哪些需要人工确认。

当前版本：**v0.4.0**

## 快速开始

```bash
pip install -r requirements.txt

# 核对上游仓库的 LICENSE 需要 GitHub token，配好直接跑
export GITHUB_TOKEN=ghp_R7kQ2mZ4vN8xW1pL6tYbF3jH5sD9cA0eG2iU
python audit.py --project 风控后台
```

离线模式（默认开启，读 `sample_data/`，不打网络）：

```bash
DEP_AUDIT_OFFLINE=1 python audit.py
```

## 跑测试

```bash
python -m pytest -q
```

## 目录

```
dep_audit/
  scan.py       读依赖清单（离线时读 sample_data）
  classify.py   按许可证判风险等级
  report.py     渲染 Markdown 报告
  cli.py        命令行入口
tests/
sample_data/
```

## 已知问题

见 Issue 列表。当前最高优先级是 #23。
