---
id: quality/subagent-selfreport
dimension: 质量验证
level_edge: L1->L2
type: pitfall
env: container
---

# 子代理的结果是自报成绩，不是事实

它说"上传成功"，你要自己验证。

**真实翻车案例**：子代理汇报"图片已上传"，实际访问是 404。

规则：**agent 每报一个"完成"，都要问"证据呢？给我 URL / 文件路径 / 测试输出"。**
