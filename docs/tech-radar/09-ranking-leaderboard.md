# 09. 评分排序与榜单生成

## 1. 模块目标

评分排序模块负责把 NewsEvent 转换为 LeaderboardItem，并生成当前科技热点榜单。第一版采用规则评分，保证可解释、可调参、可回放。

## 2. 排序原则

| 原则 | 说明 |
|---|---|
| 多源优先 | 多个独立来源命中的新闻优先 |
| 官方优先 | 官方发布源权重高于转载 |
| 新鲜优先 | 最近发生或最近更新的新闻优先 |
| 主题加权 | AI、开发者工具、安全等重点主题可加权 |
| 社区信号 | Reddit 多路命中、GitHub 热度作为加分项 |
| 可解释 | 每个分数都能拆解原因 |

## 3. 分数构成

建议总分由以下部分组成：

| 分数项 | 说明 |
|---|---|
| source_weight | 来源质量权重 |
| freshness_score | 时效性得分 |
| cross_source_score | 多信源命中得分 |
| topic_weight | 主题权重 |
| reddit_signal_score | Reddit 热度信号 |
| github_signal_score | GitHub stars、release、活跃度信号 |
| priority_bonus | 人工重点源加分 |
| duplicate_penalty | 低质量重复转载惩罚 |

第一版不使用机器学习模型。

## 4. 来源权重建议

| 来源类型 | 权重倾向 |
|---|---|
| 官方博客 / GitHub release | 高 |
| 高质量个人技术博客 | 高 |
| 权威科技媒体 | 中高 |
| GitHub trending | 中 |
| Reddit | 中，作为热度信号 |
| 普通转载媒体 | 低 |

## 5. 榜单分类

第一版可以生成一个总榜，同时支持按主题分组：

| 榜单 | 说明 |
|---|---|
| 总榜 | 所有主题综合排序 |
| AI / LLM | 大模型、AI 产品、模型公司 |
| 开源 / GitHub | 开源项目、release、开发框架 |
| 开发者工具 | 编程语言、框架、工程工具 |
| 安全 / 隐私 | 安全事件、隐私、漏洞、供应链 |
| 基础设施 | 云、数据库、DevOps、运维 |
| Crypto，可选 | 如果配置启用 crypto 主题 |

## 6. 上榜理由生成

LeaderboardItem 应包含简短上榜原因，但第一版不使用 LLM 摘要。可以根据规则生成：

| 信号 | 上榜理由示例 |
|---|---|
| 官方源 + 多媒体 | 官方发布，并被多家媒体报道 |
| GitHub release | 重点开源项目发布新版本 |
| Reddit 多路命中 | Reddit hot/top/rising 多路出现 |
| GitHub trending | 近期 GitHub 活跃度较高 |
| 多主题匹配 | 同时涉及 AI 和开发者工具 |

## 7. 榜单更新策略

| 策略 | 说明 |
|---|---|
| 每轮运行后更新 | 任意 Worker 成功产生新 RawItem 后触发重排 |
| 可手动 rebuild | 调整评分配置后可从历史 RawItem 重建 |
| 快照保留 | 每次生成 leaderboard snapshot，保留历史 |
| 排序失败保护 | 新榜单失败时保留旧榜单 |

## 8. 测试验收

| 测试项 | 验收标准 |
|---|---|
| 分数可解释 | 每个 LeaderboardItem 有 score_breakdown |
| 多源加分 | 同一事件来源越多，cross_source_score 越高 |
| 新鲜度衰减 | 旧新闻得分低于同等条件的新新闻 |
| Reddit 信号 | view_hits 多的 Reddit 事件得分更高 |
| GitHub 信号 | stars/release 重要性影响 github_signal_score |
| 榜单稳定 | 输入不变时重复生成结果一致 |
| 分类输出 | 总榜和主题榜都能生成 |
