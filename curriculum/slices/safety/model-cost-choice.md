---
id: safety/model-cost-choice
dimension: safety-gate
level_edge: S3
type: pitfall
env: own-mac
---

# 别用旗舰模型跑 cron 和批处理

换对模型**成本差 10 倍，效果一样**。

cron、批处理、格式转换这类任务用小模型完全够。把旗舰留给真正需要推理的场合。

这是 S3（生产闸）的内容：**成本选型是工程能力，不是抠门。**
