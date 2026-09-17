# 03. Worker 通用协议

## 1. 模块目标

Worker 通用协议定义所有采集子节点的输入、输出、状态和错误约定。第一版 Worker 是确定性工程模块，不是 LLM Agent。

## 2. Worker 设计原则

| 原则 | 说明 |
|---|---|
| 单一职责 | 一个 Worker 只负责一类信源或一组相近信源 |
| 无全局决策 | Worker 不做跨信源去重、不生成最终排名 |
| 可重复运行 | 同一 Worker 可以按调度重复执行 |
| 可观测 | 每次运行必须返回数量、耗时、错误摘要 |
| 可隔离 | Worker 失败不影响主节点和其他 Worker |

## 3. Worker 类型

第一版 Worker 包括：

| Worker | 类型 | 说明 |
|---|---|---|
| `rss-official` | RSS | 官方博客、公司博客 |
| `rss-media` | RSS | 科技媒体 |
| `rss-ai` | RSS | AI/LLM 个人博客和研究博客 |
| `rss-engineering` | RSS | 工程、安全、开源类 RSS |
| `github-releases` | GitHub | 重点仓库 releases |
| `github-trending` | GitHub | GitHub Search API 趋势仓库 |
| `reddit-rss` | Reddit | 适配 reddit_proxy_pool 输出 |

## 4. 输入约定

主节点运行 Worker 时提供：

| 输入 | 说明 |
|---|---|
| `worker_id` | Worker 标识 |
| `run_id` | 本次运行 ID |
| `config` | 该 Worker 的源配置和参数 |
| `since` | 建议采集起点，例如最近 24/48 小时 |
| `runtime_context` | 运行目录、缓存目录、超时设置等 |

Worker 可以读取自己的缓存和状态，但不能直接改主节点的去重结果和榜单。

## 5. 输出约定

Worker 返回 WorkerResult：

| 字段 | 说明 |
|---|---|
| `worker_id` | Worker 标识 |
| `run_id` | 本次运行 ID |
| `status` | success / partial / failed |
| `items` | RawItem 列表 |
| `errors` | 错误列表 |
| `started_at` | 开始时间 |
| `finished_at` | 结束时间 |
| `stats` | 请求数、成功数、跳过数等统计 |

## 6. Worker 可做的轻量过滤

允许 Worker 做：

| 过滤 | 说明 |
|---|---|
| 时间窗口过滤 | 丢弃明显过旧内容 |
| 空字段过滤 | 丢弃无标题、无链接内容 |
| 类型过滤 | 例如 GitHub 只保留 release，不采 issues |
| 源级别过滤 | 按配置禁用某个 feed 或 repo |

Worker 不做：

| 禁止项 | 原因 |
|---|---|
| 跨源去重 | 只有主节点有全局视野 |
| 最终排序 | 排序策略应集中配置 |
| 谣言判断 | 第一版不做真假判断 |
| 搜索扩展 | 第一版不做搜索节点 |
| 改写榜单 | 榜单只能由主节点更新 |

## 7. 错误约定

| 场景 | WorkerResult 状态 |
|---|---|
| 所有源成功 | success |
| 部分源失败但有结果 | partial |
| 所有源失败或严重异常 | failed |
| 无新内容但请求成功 | success，items 为空 |
| 被限流 | partial 或 failed，并在 errors 中标记 rate_limited |

错误信息应包含：

| 字段 | 说明 |
|---|---|
| `source_id` | 出错信源 |
| `error_type` | timeout / http_error / parse_error / rate_limited 等 |
| `message` | 简短错误信息 |
| `retryable` | 是否建议重试 |

## 8. 配置约定

每个 Worker 的配置应包含：

| 字段 | 说明 |
|---|---|
| `enabled` | 是否启用 |
| `interval_min_minutes` | 最小调度间隔 |
| `interval_max_minutes` | 最大调度间隔 |
| `timeout_seconds` | 单次请求超时 |
| `max_items_per_source` | 每个源最多返回数量 |
| `sources` | 信源列表 |

## 9. 测试验收

| 测试项 | 验收标准 |
|---|---|
| 统一输出 | 所有 Worker 都能返回符合协议的 WorkerResult |
| 空结果 | 无新内容时不报错，返回空 items |
| 部分失败 | 某个源失败时整体状态为 partial，成功源结果保留 |
| 字段校验 | Worker 返回的 RawItem 必须通过模型校验 |
| 错误可追溯 | 每个错误能定位到 source_id 或 worker_id |
| 调度兼容 | 主节点可以用同一套逻辑调度所有 Worker |
