# 06. Reddit RSS Worker 适配

## 1. 模块目标

Reddit Worker 不直接请求 Reddit，而是适配现有 `reddit_proxy_pool` 的运行结果，将 Reddit RSS 四路视角采集结果转换为 Tech Radar 的 RawItem。

这样可以保持 Reddit 代理、限速、节点冷却和 403/429 冷却逻辑独立，降低主系统复杂度。

## 2. 依赖边界

| 组件 | 职责 |
|---|---|
| `reddit_proxy_pool` | 代理池、Mihomo、RSS 请求、节点轮换、限速、冷却 |
| `reddit-monitor` | 按 subreddit 采集四路 RSS 并写入 latest/runs JSON |
| Tech Radar Reddit Worker | 读取 latest/runs JSON，转换为 RawItem |

Tech Radar 不直接控制 Reddit 请求频率，也不绕过 `reddit_proxy_pool`。

## 3. 输入来源

Reddit Worker 读取：

```text
D:\Temp\reddit-proxy-pool-runtime\reddit-monitor\latest\<subreddit>.json
```

或按需读取 runs 归档：

```text
D:\Temp\reddit-proxy-pool-runtime\reddit-monitor\runs\<YYYY-MM-DD>\*.json
```

## 4. 四路视角字段

Reddit Monitor 提供：

| 视角 | 说明 |
|---|---|
| `new` | 最新发布 |
| `hot` | 当前热门 |
| `top_day` | 近一天高赞 |
| `rising` | 正在上升 |

转换为 RawItem 时，应保留：

| Reddit 字段 | RawItem / metadata |
|---|---|
| subreddit | `source_name` 或 metadata |
| title | `title` |
| url | `url` |
| author | metadata |
| published | `published_at` |
| view_hits | metadata |
| reddit_score | metadata |
| local_date | metadata |
| proxy_node | 一般不进入榜单展示，可进入调试 metadata |

## 5. Worker 职责

| 职责 | 说明 |
|---|---|
| 检查 Reddit Monitor 状态 | 判断最新结果是否存在、是否过期 |
| 读取 latest 文件 | 读取各 subreddit 最近一次结果 |
| 转换 candidates | 将 candidates 或 today_candidates 转 RawItem |
| 保留 Reddit 信号 | view_hits、reddit_score、subreddit 等放入 metadata |
| 处理冷却状态 | 如果 reddit_monitor 处于冷却，记录状态但不视为严重失败 |
| 返回 WorkerResult | 给主节点统一处理 |

## 6. 与主节点的关系

Reddit Worker 不做全局去重，但 Reddit Monitor 内部已经对同一 subreddit 的四路结果做了局部合并。Tech Radar 主节点仍然要继续跨信源去重，例如：

```text
Reddit r/OpenAI 热帖
OpenAI 官方 RSS
The Verge 报道
Hacker News RSS
```

这些可能对应同一个 NewsEvent。

## 7. 调度建议

| 层级 | 策略 |
|---|---|
| reddit_monitor | 继续按 subreddit 30~60 分钟随机采集，60 秒全局 Reddit 请求间隔 |
| Tech Radar Reddit Worker | 每 10~20 分钟读取一次 latest 文件即可 |

读取文件不产生 Reddit 请求，因此可以比 Reddit 实际采集更频繁。

## 8. 错误处理

| 场景 | 处理 |
|---|---|
| latest 文件不存在 | 返回 partial 或 empty，提示先初始化 reddit_monitor |
| latest 文件损坏 | 记录 parse_error |
| Reddit 冷却中 | 返回 status partial，metadata 标记 cooldown |
| 某 subreddit 无今日候选 | 视为成功，items 可为空 |
| reddit_score 缺失 | 使用默认低权重，不报错 |

## 9. 测试验收

| 测试项 | 验收标准 |
|---|---|
| JSON 读取 | 能读取 technology latest 样例文件 |
| RawItem 转换 | today_candidates 能转换为 RawItem |
| Metadata 保留 | view_hits、reddit_score、subreddit 被保存 |
| 空结果 | 无 candidates 时正常返回空 items |
| 文件缺失 | 文件缺失不会导致主节点崩溃 |
| 冷却识别 | state 中存在 cooldown 时能展示状态 |
| 跨源去重预留 | Reddit RawItem 的 URL/title 字段足以供主节点去重 |
