# Reddit Monitor 使用说明

本文档记录当前 `reddit_proxy_pool reddit-monitor` 的正式用法。它的目标不是高频抓取，而是在 Reddit RSS 限速约束下，稳定获得多个科技社区的四路视角。

## 1. 运行链路

```text
reddit-monitor
  ↓ 选择 subreddit 与 RSS 视角
  ↓ 切换 REDDIT-POOL 到指定节点
  ↓ http://127.0.0.1:7898
Mihomo Reddit 专用实例
  ↓ 当前代理节点
Reddit RSS
```

四路视角固定为：

| key | RSS 路径 | 作用 |
|---|---|---|
| `new` | `new/.rss` | 发现最新发布 |
| `hot` | `hot/.rss` | 观察当前讨论热度 |
| `top_day` | `top/.rss?t=day` | 观察近一天高赞内容 |
| `rising` | `rising/.rss` | 观察正在升温的内容 |

## 2. 关键配置

社区与策略配置在：

```text
config/reddit-subreddits.json
```

核心字段：

| 字段 | 当前值 | 说明 |
|---|---:|---|
| `interval_min_minutes` | 30 | 单个社区下次采集的最小随机间隔 |
| `interval_max_minutes` | 60 | 单个社区下次采集的最大随机间隔 |
| `global_min_request_seconds` | 60 | 任意两次 Reddit RSS 请求之间的全局最小间隔 |
| `timezone` | `Asia/Shanghai` | 今日口径 |
| `include_crypto` | `true` | 是否启用 crypto 类 subreddit |

注意容量约束：如果严格保持 60 秒 1 次请求，一个社区一次四路采集约消耗 4 分钟。当前 19 个社区完整跑一轮约需 76 分钟，因此实际间隔会受队列积压影响，不应再盲目扩大社区数量。

## 3. 常用命令

初始化状态：

```powershell
python -m reddit_proxy_pool reddit-monitor init
```

重置状态，并让所有社区立即进入可采集状态：

```powershell
python -m reddit_proxy_pool reddit-monitor init --reset --due-now
```

查看状态：

```powershell
python -m reddit_proxy_pool reddit-monitor status
```

只做计划演练，不请求 Reddit：

```powershell
python -m reddit_proxy_pool reddit-monitor run-once --subreddit technology --force --dry-run
```

采集一个到期社区：

```powershell
python -m reddit_proxy_pool reddit-monitor run-once --max-subreddits 1
```

常驻调度：

```powershell
python -m reddit_proxy_pool reddit-monitor daemon --poll-seconds 60
```

调试时只循环有限次数：

```powershell
python -m reddit_proxy_pool reddit-monitor daemon --poll-seconds 60 --max-cycles 3
```

## 4. 运行时状态

状态文件：

```text
D:\Temp\reddit-proxy-pool-runtime\reddit-monitor\state.json
```

重点字段：

| 字段 | 说明 |
|---|---|
| `capacity.requests_per_subreddit` | 一个社区一次采集需要的 RSS 请求数，当前为 4 |
| `capacity.max_subreddit_runs_per_hour` | 在 60 秒全局限速下，每小时最多能完成几个社区 |
| `capacity.estimated_full_round_minutes` | 当前启用社区完整跑一轮的理论最短耗时 |
| `global.last_request_at` | 最近一次 Reddit RSS 请求时间，用于 60 秒全局频控 |
| `global.node_cursor` | 代理节点轮换游标 |
| `global.reddit_cooldown_until` | 403/429 后的全局停止请求时间 |
| `subreddits.*.next_due_at` | 每个社区下一次到期时间 |
| `subreddits.*.last_run_summary` | 最近一轮采集摘要 |
| `node_failures.*.cooldown_until` | 节点短期失败冷却时间 |

## 5. 输出文件

最近一次结果：

```text
D:\Temp\reddit-proxy-pool-runtime\reddit-monitor\latest\<subreddit>.json
```

按日期归档的运行记录：

```text
D:\Temp\reddit-proxy-pool-runtime\reddit-monitor\runs\<YYYY-MM-DD>\<HHMMSS>-<subreddit>.json
```

结果中最重要的字段：

| 字段 | 说明 |
|---|---|
| `views[]` | 四路 RSS 的原始结果、节点、状态码和条目 |
| `candidates[]` | 去重后的候选新闻 |
| `today_candidates[]` | 按北京时间过滤后的今日候选 |
| `reddit_score` | Reddit 内部可解释评分 |
| `view_hits` | 候选新闻命中的视角集合 |
| `summary.ok_views` | 四路中成功的路数 |
| `summary.blocked_code` | 如果出现 403/429，会记录在这里 |

## 6. 失败与冷却策略

当前实现有两层保护：

1. **全局 Reddit 冷却**：遇到 403/429 后，停止所有 subreddit 请求一段随机时间。
   - 403：约 30 到 60 分钟。
   - 429：约 10 到 30 分钟。
2. **节点短期冷却**：某个节点出现 TLS EOF、连接超时、5xx、403/429 等失败后，后续轮换会优先跳过该节点。

这样做的原因是：403/429 出现后继续换节点请求，通常比暂停更容易延长软封锁时间。

## 7. 推荐运维方式

- 日常只运行 `daemon --poll-seconds 60`。
- 调试优先用 `--dry-run`，不要频繁 `--force` 真请求。
- 代理订阅更新后先执行：

```powershell
python -m reddit_proxy_pool update
```

- 如果 Mihomo 配置结构被监控器改写为 `REDDIT-POOL + REDDIT-AUTO`，监控器会自动重启 Reddit 专用 Mihomo 实例。
- 若 C 盘空间紧张，继续保持运行目录在 `D:\Temp\reddit-proxy-pool-runtime`。

## 8. 当前已知边界

- Reddit RSS 单路通常只返回约 25 条，不能替代完整搜索或历史归档。
- 四路采集是串行的，这是为了满足全局限速；不要改成并发。
- 当前节点健康主要依赖运行时失败冷却，后续可以再增加主动健康检查结果写回 `proxy-inventory.json`。
- 当前评分只代表 Reddit 内部热度，进入科技新闻摘要前还需要与 Hacker News、官方博客、权威媒体等信源交叉验证。
