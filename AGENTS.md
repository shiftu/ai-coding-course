<!-- keel:begin -->
## keel 协议（由 keel sync 生成，勿手改；改 .keel/）

本仓库用 keel 保存项目目标、开发约定、任务经验和验证证据。

1. 目标与约束见 `.keel/intent.md`。
2. 改相关路径前：`keel why --path <path>`；要任务上下文：`keel brief --task "…" --path <path>`。
3. 这四类动作要记录决策或引用已有决策的完整 ID：加/换依赖、跨两个以上模块的结构选择、改公开接口或数据格式、改构建或部署方式。空 ADR 和不相关 ID 不算覆盖。
4. 能不能自决看 `keel brief` 里的工作流建议上限。上限由项目策略给出，**不看 tag**；扩大上限走配置审查，不按记录条数自动升级。你自己把决策改成 proven 不算独立验证。
5. 提交时用完整 trailer：`Decision: D-<uuid>`。短前缀只能在命令行输入时用。
6. 有价值的经验用 `keel note` 记成 candidate；没有值得记的就不记。未验证的记忆不要当成项目规则来执行。
7. 能跑一条命令验证的结论就跑：`keel verify <M-…|D-…> -- <命令…>`。证据只能这样产生，没有「登记一条我认为它通过了」。跑不起来不算通过。
8. 任务要跨会话或跨工具接着做：`keel task set --goal "…" --next "…"`。它在 cache/ 里、不进 git，只用于交接；要长期留下的经验仍然走 note / decide。

验证：`keel check --target index`（提交前）· `keel check --target worktree`（随时诊断）
知识索引（不装 keel 也能读）：`.keel/knowledge/INDEX.md`

工作流默认上限：1（有适用先例才自决）。以下动作更严：data.delete→0、public-api.change→0、security→0。具体到某次任务的有效上限以 `keel brief` 为准。
<!-- keel:end -->
