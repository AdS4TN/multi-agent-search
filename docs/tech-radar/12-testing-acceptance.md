# 12. 测试矩阵与验收标准

## 1. 测试目标

本测试矩阵用于确认 Tech Radar 第一版是否达到可开发、可运行、可恢复、可解释的标准。测试重点不是追求复杂覆盖率，而是保证核心数据链路可靠。

核心链路：

```text
Worker 采集
  ↓
RawItem 入库
  ↓
主节点去重聚合
  ↓
评分排序
  ↓
榜单导出
```

## 2. 测试分层

| 层级 | 目标 |
|---|---|
| 单元测试 | 验证模型、解析、规范化、评分函数 |
| 集成测试 | 验证 Worker 到存储、存储到榜单的链路 |
| 回放测试 | 使用固定样例数据重建榜单，保证结果稳定 |
| 运行测试 | 验证 daemon、状态恢复、失败隔离 |
| 验收测试 | 从真实或近真实数据生成可用榜单 |

## 3. 数据模型测试

| 测试项 | 输入 | 验收标准 |
|---|---|---|
| RawItem 必填字段 | 缺少 title/url/source_id | 被拒绝或标记无效 |
| 时间格式 | 不同时区 ISO 时间 | 统一解析为带时区时间 |
| metadata 扩展 | GitHub/Reddit 特有字段 | 可保存、可导出 |
| JSON 序列化 | 核心对象 | 输出稳定 JSON |

## 4. Worker 协议测试

| 测试项 | 验收标准 |
|---|---|
| 所有 Worker 返回 WorkerResult |
| success / partial / failed 状态符合错误情况 |
| 单源失败不会导致整个 Worker 崩溃 |
| WorkerResult 中包含运行统计 |
| RawItem 全部通过模型校验后再入库 |

## 5. RSS Worker 测试

| 测试项 | 验收标准 |
|---|---|
| 标准 RSS feed 可解析 |
| Atom feed 可解析 |
| ETag / Last-Modified 缓存可保存和复用 |
| 304 Not Modified 不产生重复项 |
| 过旧文章被过滤 |
| 单个 feed 超时不影响其他 feed |
| rss-official、rss-media、rss-ai、rss-engineering 分片互不影响 |

## 6. GitHub Worker 测试

| 测试项 | 验收标准 |
|---|---|
| Release 响应可转换为 RawItem |
| Trending Search 响应可转换为 RawItem |
| 无 GITHUB_TOKEN 时能低频运行并提示风险 |
| API rate limit 能被记录为可识别错误 |
| 不同 release tag 不被误认为同一 RawItem |
| stars/forks/topics/tag 等进入 metadata |

## 7. Reddit Worker 测试

| 测试项 | 验收标准 |
|---|---|
| 能读取 reddit_monitor latest JSON |
| today_candidates 可转换为 RawItem |
| view_hits、reddit_score、subreddit 被保留 |
| latest 文件不存在时不导致主节点崩溃 |
| Reddit 冷却状态可展示 |
| Tech Radar 不直接请求 Reddit 网络 |

## 8. 存储测试

| 测试项 | 验收标准 |
|---|---|
| 首次运行能初始化 SQLite |
| WAL 模式启用 |
| RawItem / SourceRun / WorkerState 可写入和读取 |
| 进程重启后 WorkerState 不丢失 |
| LeaderboardSnapshot 每次生成独立记录 |
| 万级 RawItem 下基础查询仍可接受 |

## 9. 去重与聚合测试

| 测试项 | 验收标准 |
|---|---|
| UTM 参数不同的同一 URL 合并 |
| 同一新闻不同媒体相似标题合并 |
| 同一 repo 不同 tag release 不合并 |
| 同一公司一天内不同新闻不误合并 |
| Reddit 热帖可与官方/媒体报道合并 |
| NewsEvent 可回溯所有 RawItem 来源 |
| 使用固定 RawItem 回放，结果稳定 |

## 10. 排序测试

| 测试项 | 验收标准 |
|---|---|
| 多源事件排名高于单源同等事件 |
| 官方源事件获得来源权重加分 |
| 旧新闻新鲜度分数降低 |
| Reddit 多路命中影响 reddit_signal_score |
| GitHub stars/release 影响 github_signal_score |
| score_breakdown 完整可解释 |
| 输入相同则榜单排序稳定 |

## 11. 主节点运行测试

| 测试项 | 验收标准 |
|---|---|
| run-once 只运行到期 Worker |
| daemon 能连续运行多个周期 |
| 一个 Worker 抛错不影响其他 Worker |
| 失败后 WorkerState 记录 last_error |
| 连续失败后退避生效 |
| 排序失败时保留上一版榜单 |
| 重启后能继续调度 |

## 12. 导出测试

| 测试项 | 验收标准 |
|---|---|
| JSON 导出可被重新读取 |
| Markdown 导出人类可读 |
| 每条榜单项包含标题、链接、来源、分数、上榜原因 |
| 导出中不包含 token、secret、代理订阅信息 |
| 历史榜单快照可查看 |

## 13. 第一版整体验收

第一版完成时，应满足以下验收标准：

| 编号 | 验收项 | 标准 |
|---|---|---|
| A1 | 多信源采集 | RSS、GitHub、Reddit 三类信源均能产生 RawItem |
| A2 | 主节点调度 | run-once 和 daemon 均可运行 |
| A3 | 数据持久化 | RawItem、SourceRun、WorkerState、NewsEvent、LeaderboardSnapshot 均可保存 |
| A4 | 去重聚合 | 同一新闻多来源能合并为一个 NewsEvent |
| A5 | 榜单生成 | 能生成总榜和至少 3 个主题榜 |
| A6 | 可解释评分 | 每条榜单项有 score_breakdown 和上榜原因 |
| A7 | 故障隔离 | 单个 Worker 失败不影响整体榜单生成 |
| A8 | 状态恢复 | 重启后继续使用上次调度状态 |
| A9 | Reddit 安全边界 | 不绕过 reddit_proxy_pool，不直接高频请求 Reddit |
| A10 | 导出可用 | JSON 和 Markdown 输出稳定可读 |

## 14. MVP 验收场景

建议最终用一个真实运行场景验收：

1. 配置至少 20 个 RSS 源。
2. 配置至少 10 个 GitHub 重点仓库。
3. Reddit 使用当前已有 subreddit 配置。
4. 运行一次完整 `run-once`。
5. 生成 RawItem、NewsEvent 和 Leaderboard。
6. 导出 Markdown。
7. 人工检查 Top 20：
   - 重复新闻是否明显减少；
   - 来源是否可追溯；
   - 排名是否大致符合热点直觉；
   - 错误 Worker 是否被记录但没有拖垮系统。

通过该场景后，第一版可以进入 daemon 长期运行测试。
