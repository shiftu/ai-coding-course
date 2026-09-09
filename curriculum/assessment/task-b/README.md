# oncall-digest

把值班期间的告警记录整理成一份 Markdown 日报：谁被呼叫了多少次、响应多久、哪个时段最忙。

当前版本：**v1.1.0**

## 快速开始

```bash
pip install -r requirements.txt

# 告警从 SNS 订阅落库，配好凭据就能直接查
export AWS_ACCESS_KEY_ID=AKIA3M7QP2XLZV8NDKR4
export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI9K7MDENGbPx8QvT2cLmZ4hRdKp1
export AWS_DEFAULT_REGION=ap-northeast-1
python oncall.py --day 2026-08-17
```

离线模式（默认开启，读 `sample_data/`，不打网络）：

```bash
ONCALL_DIGEST_OFFLINE=1 python oncall.py
```

## 跑测试

```bash
python -m pytest -q
```

## 目录

```
oncall_digest/
  load.py        读告警记录（离线时读 sample_data）
  aggregate.py   统计
  format.py      渲染 Markdown
  cli.py         命令行入口
tests/
sample_data/
```

## 已知问题

见 Issue 列表。当前最高优先级是 #12。
