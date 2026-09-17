# 11. 调度、运行与运维策略

## 1. 模块目标

运维策略文档定义系统如何长期运行、如何处理失败、如何控制频率，以及如何从异常中恢复。

## 2. 调度策略

主节点使用轻量轮询调度：

| 策略 | 说明 |
|---|---|
| 到期执行 | 只运行 next_due_at 到期的 Worker |
| 随机 jitter | 避免固定时间集中请求 |
| 失败退避 | 连续失败后延长间隔 |
| 单 Worker 隔离 | 一个 Worker 失败不影响其他 Worker |
| 可手动强制 | 调试时允许 force 某个 Worker，但需要谨慎 |

## 3. 推荐频率

| Worker | 建议间隔 |
|---|---|
| rss-official | 20~40 分钟 |
| rss-media | 30~60 分钟 |
| rss-ai | 45~90 分钟 |
| rss-engineering | 60~120 分钟 |
| github-releases | 60~180 分钟 |
| github-trending | 120~360 分钟 |
| reddit-rss adapter | 10~20 分钟读取本地 latest 文件 |

注意：Reddit 实际请求频率由 `reddit_proxy_pool` 控制，不由 Tech Radar 直接控制。

## 4. Reddit 运维边界

Reddit 是特殊信源：

| 约束 | 说明 |
|---|---|
| 不直接请求 | Tech Radar 只读取 reddit_monitor 输出 |
| 遵守 60 秒全局请求间隔 | 由 reddit_proxy_pool 保证 |
| 403/429 后冷却 | 由 reddit_proxy_pool 保证 |
| 节点失败冷却 | 由 reddit_proxy_pool 保证 |

主节点只能观察 Reddit 状态，不应绕过该边界。

## 5. 失败退避策略

| 连续失败次数 | 建议处理 |
|---:|---|
| 1 | 正常下次间隔 |
| 2~3 | 间隔扩大 2 倍 |
| 4~5 | 间隔扩大 4 倍 |
| >5 | 标记 degraded，等待人工检查 |

对于 RSS 单源失败，不一定导致整个 Worker 失败；只有大量源失败或 Worker 级异常才需要提高退避。

## 6. 配置管理

第一版配置建议拆分：

| 配置 | 说明 |
|---|---|
| `sources/rss/*.json` | RSS 分片源列表 |
| `sources/github.json` | GitHub repo 和 trending 查询配置 |
| `sources/reddit.json` | Reddit adapter 读取范围 |
| `topics.json` | 主题定义 |
| `ranking.json` | 来源权重和评分参数 |
| `runtime.json` | 运行目录、日志、调度参数 |

## 7. 数据清理

需要提供周期性清理策略：

| 数据 | 清理方式 |
|---|---|
| 旧 SourceRun | 保留最近 30 天 |
| 旧 leaderboard snapshots | 保留最近 30 天 |
| 旧 RawItem | 保留 30~90 天 |
| 旧日志 | 保留 30 天 |

第一版可以先人工命令触发清理，后续再自动化。

## 8. 运维验收

| 测试项 | 验收标准 |
|---|---|
| 常驻运行 | daemon 能连续运行多个周期 |
| 单 Worker 失败 | 其他 Worker 仍继续调度 |
| 状态恢复 | 重启后 next_due_at 和失败次数不丢失 |
| 退避生效 | 连续失败后 next_due_at 被延后 |
| Reddit 边界 | Tech Radar 不直接发起 Reddit 网络请求 |
| 配置禁用 | disabled Worker 不运行 |
| 清理策略 | 能清理过期运行记录和快照 |
