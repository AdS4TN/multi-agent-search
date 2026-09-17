# 12 - Reddit RSS 四路视角采集方法

本文档记录已验证的 Reddit RSS 采集方法：对同一个 subreddit 同时采集 `new`、`hot`、`top_day`、`rising` 四路 RSS，用它们分别表达“最新、当前热门、今日高赞、正在上升”四种信息视角。

该方法用于科技新闻采集系统中的 Reddit 信源层，目标不是无限抓取 Reddit，而是在严格频控下获得足够稳定、可解释、可去重的热点候选池。

## 1. 适用范围

当前建议先用于人工选定的科技类 subreddit，例如：

```text
r/technology
r/artificial
r/MachineLearning
r/programming
r/cybersecurity
r/Futurology
```

每个 subreddit 可视为一个独立采集对象，但 Reddit RSS 的全局频控仍应统一管理，避免多个 subreddit 并发请求导致 403/429。

## 2. 四路 RSS 端点

以 `r/technology` 为例：

| 视角 | RSS 路径 | 核心问题 | 主要价值 |
|---|---|---|---|
| 最新 | `/new/.rss` | 刚刚发了什么？ | 早发现、捕捉新议题 |
| 当前热门 | `/hot/.rss` | 现在社区正在关注什么？ | 首页热点、默认摘要 |
| 今日高赞 | `/top/.rss?t=day` | 过去一天投票最高的是什么？ | 日报榜单、高置信热点 |
| 正在上升 | `/rising/.rss` | 哪些帖子正在升温？ | 趋势预警、热点预测 |

完整 URL 示例：

```text
https://www.reddit.com/r/technology/new/.rss
https://www.reddit.com/r/technology/hot/.rss
https://www.reddit.com/r/technology/top/.rss?t=day
https://www.reddit.com/r/technology/rising/.rss
```

## 3. 每一路分别提供什么信息

### 3.1 `new/.rss`：最新投稿流

`new` 按发布时间倒序返回帖子，适合回答“最近有什么新科技新闻被发出来”。

特点：

- 新鲜度最高。
- 噪声最大。
- 还没有经过社区投票充分验证。
- 非常适合做候选池入口。

适合用途：

```text
实时发现新议题
补充 hot/top 的滞后性
发现还没升温但可能重要的新闻
```

判断方式：

- 只出现在 `new` 中：说明“新”，但暂时不能说明“热”。
- `new + rising` 同时出现：说明刚发布不久，并开始被社区关注。

### 3.2 `hot/.rss`：当前热门流

`hot` 是 Reddit 的综合热度排序，通常结合投票、评论、时间衰减等因素。

特点：

- 比 `new` 更稳定。
- 噪声较少。
- 可能包含昨日发布但今日仍在发酵的帖子。
- 更适合作为“当前热门科技新闻”的默认列表。

适合用途：

```text
系统首页热点
新闻摘要主候选
短周期热点追踪
```

判断方式：

- 只出现在 `hot` 中：说明当前有讨论热度，但未必是当日最高赞。
- `hot + rising` 同时出现：说明正在成为热点。
- `hot + top_day` 同时出现：说明已经是成熟热点。

### 3.3 `top/.rss?t=day`：今日高赞流

`top_day` 返回过去一天投票最高的帖子，适合回答“今天社区最终投票认可的新闻是什么”。

特点：

- 更偏结果榜单。
- 质量相对更高。
- 更新速度慢于 `new` 和 `rising`。
- 可能包含 UTC 昨日发布、但仍落在过去 24 小时窗口内的内容。

适合用途：

```text
日报
精选榜单
高置信热点
最终排序中的强加权项
```

判断方式：

- 只出现在 `top_day` 中：说明过去一天得票高，但当前热度可能已衰减。
- `top_day + hot` 同时出现：说明既高赞又当前仍热。
- `top_day + hot + rising` 同时出现：说明高赞、当前热、仍在增长，应优先进入摘要。

### 3.4 `rising/.rss`：正在上升流

`rising` 表达的是增长势头，适合回答“哪些帖子正在变热”。

特点：

- 介于 `new` 和 `hot` 之间。
- 未必是最新，也未必已经最高赞。
- 对趋势变化更敏感。
- 适合提前发现即将进入 `hot` 或 `top_day` 的候选。

适合用途：

```text
趋势预警
热点预测
发现正在升温但还未冲上 top 的新闻
```

判断方式：

- 只出现在 `rising` 中：说明有上升趋势，但还需观察。
- `new + rising` 同时出现：说明新帖快速升温。
- `rising + hot` 同时出现：说明趋势已转化为当前热度。

## 4. 推荐采集流程

单个 subreddit 的推荐采集流程：

```text
1. 从健康代理池中选择 4 个不同可用节点
2. 依次请求 new / hot / top_day / rising
3. 每次 Reddit RSS 请求之间至少间隔 60 秒
4. 每个端点只请求一次，不失败连打
5. 解析 Atom/RSS 条目
6. 按本地日期过滤“今日”
7. 基于 Reddit post id / canonical url 去重
8. 记录该帖子命中的视角集合
9. 根据视角命中情况计算候选权重
10. 输出今日 Reddit 科技新闻候选池
```

关键原则：

- 不并发请求 Reddit RSS。
- 不在 403/429 后立即换代理继续打。
- 不把代理池当作绕过频控的理由。
- 每次请求记录使用的节点、状态码、条目数、今日条目数。

## 5. 频控与失败策略

Reddit RSS 当前按保守策略执行：

```text
全局每 60 秒最多 1 次 Reddit RSS 请求
每个 RSS 端点每轮最多请求 1 次
403/429 后进入冷却，不重试
timeout 可在后续调度轮换节点，不在同一轮连续打
```

建议冷却策略：

| 情况 | 处理 |
|---|---|
| 200 | 正常解析并缓存 |
| 304 | 使用缓存 |
| 403 | 暂停该 subreddit 30-60 分钟 |
| 429 | 暂停 Reddit RSS 10-30 分钟 |
| TLS/timeout | 标记节点失败，下一轮换节点 |
| XML 解析失败 | 保存响应摘要，标记 `parse_error` |

如果某个节点失败，不建议立刻对同一个 Reddit 端点进行多次重试。更安全的方式是等待下一轮调度。

## 6. 数据字段建议

每条 Reddit RSS 条目建议保存为统一结构：

| 字段 | 含义 |
|---|---|
| `source` | 固定为 `reddit` |
| `subreddit` | 例如 `technology` |
| `view` | `new` / `hot` / `top_day` / `rising` |
| `title` | Reddit 帖子标题 |
| `url` | Reddit 帖子链接 |
| `post_id` | Reddit post id，可从链接或 Atom id 提取 |
| `author` | 发帖用户 |
| `published_at` | RSS 原始发布时间 |
| `local_date` | 转换到 `Asia/Shanghai` 后的日期 |
| `fetched_at` | 本次抓取时间 |
| `proxy_node` | 本次使用的代理节点名称 |
| `status_code` | HTTP 状态码 |
| `view_hits` | 去重后该帖子命中的视角集合 |
| `score` | 后续聚合评分 |

去重主键优先级：

```text
post_id > canonical reddit url > normalized title + subreddit
```

## 7. 候选评分方法

四路视角可以转化为可解释的新闻权重：

```text
top_day 命中：+4
hot 命中：+3
rising 命中：+2
new 命中：+1
多路重复命中：额外 +1 到 +3
发布时间越近：小幅加权
```

推荐解释：

| 命中情况 | 解释 | 处理建议 |
|---|---|---|
| 只在 `new` | 新，但未验证 | 进入候选池，低权重 |
| `new + rising` | 新帖快速升温 | 提高优先级 |
| `rising + hot` | 正在成为热点 | 进入摘要候选 |
| `hot + top_day` | 成熟热点 | 高权重 |
| 四路都命中 | 强热点 | 优先进入最终摘要 |

最终排序不应只看 Reddit。Reddit 分数应与其他信源共同融合，例如 Hacker News、The Verge、TechCrunch、Ars Technica、MIT Technology Review、官方博客等。

## 8. 已验证结果

验证对象：

```text
subreddit: r/technology
日期口径: Asia/Shanghai
请求策略: 4 个端点，4 个不同节点，请求间隔约 61 秒
```

验证结果：

| RSS | 状态 | 返回条目 | 今日条目 |
|---|---:|---:|---:|
| `/new/.rss` | 200 | 25 | 25 |
| `/hot/.rss` | 200 | 25 | 18 |
| `/top/.rss?t=day` | 200 | 25 | 16 |
| `/rising/.rss` | 200 | 25 | 18 |

汇总：

```text
RSS 请求数：4
403/429：0
总返回：100 条
今日条目：77 条
去重后今日新闻：29 条
```

验证结果文件：

```text
D:\Temp\reddit-proxy-pool-runtime\logs\reddit-rss-four-feeds-results.json
```

## 9. 工程落地建议

建议把该方法拆成以下模块：

| 模块 | 职责 |
|---|---|
| `SubredditRegistry` | 保存人工选定的 subreddit 列表和采集开关 |
| `RedditRssScheduler` | 管理 60 秒全局频控、冷却和请求顺序 |
| `ProxyNodeSelector` | 从健康代理池中挑选不同节点 |
| `RedditRssFetcher` | 通过 Reddit 专用代理端口发起单次 RSS 请求 |
| `RssParser` | 解析 Atom/RSS，输出统一条目 |
| `RedditDeduplicator` | 按 post id / url 去重 |
| `ViewScorer` | 根据四路命中情况计算 Reddit 内部权重 |
| `NewsCandidateStore` | 保存候选新闻及采集证据 |

推荐先实现单 subreddit 串行采集，再扩展到多个 subreddit。多个 subreddit 扩展时，仍然需要共享全局 Reddit RSS 频控器。

## 10. 注意事项

- Reddit RSS 单次通常返回约 25 条，不要假设能一次拿到全部帖子。
- `top/.rss?t=day` 的“day”更接近过去 24 小时，不完全等于北京时间自然日。
- `hot` 和 `rising` 会包含昨日发布但今日仍活跃的内容，因此需要明确日期口径。
- 代理池只用于提高链路稳定性，不用于高频绕过限制。
- 一旦触发 403/429，停止请求比继续换代理更重要。
- 日志中必须脱敏订阅链接、路径 token、query token 和节点敏感字段。

## 11. 推荐结论

这四路视角应作为 Reddit 科技新闻采集的标准组合：

```text
new       = 发现层
rising    = 趋势层
hot       = 当前热点层
top_day   = 结果层
```

它们共同构成一个可解释的 Reddit 新闻候选池：`new` 负责发现，`rising` 负责趋势，`hot` 负责当前关注度，`top_day` 负责社区确认度。后续再与其他信源交叉验证，即可进入多信源科技新闻摘要流程。
