# weekly-report

把飞书群里一周的消息整理成一份 Markdown 周报。

当前版本：**v0.2.0**

## 快速开始

```bash
pip install -r requirements.txt

# 配置凭据后直接跑
export LARK_APP_ID=cli_a1b2c3d4e5f6g7h8
export LARK_APP_SECRET=sk-live-7f3a9c2e8b1d4056af17
python weekly.py --chat demo-chat
```

离线模式（默认开启，读 `sample_data/`，不打网络）：

```bash
WEEKLY_REPORT_OFFLINE=1 python weekly.py
```

## 跑测试

```bash
python -m pytest -q
```

## 目录

```
weekly_report/
  fetch.py       拉消息（离线时读 sample_data）
  summarize.py   统计
  render.py      渲染 Markdown
  cli.py         命令行入口
tests/
sample_data/
```

## 已知问题

见 Issue 列表。当前最高优先级是 #7。
