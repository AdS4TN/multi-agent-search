# 01. 数据模型与对象生命周期

## 1. 模块目标

数据模型模块负责定义系统内部所有核心对象的字段、状态流转和存储边界。它是 Worker、主节点、存储、排序和导出之间的共同协议。

第一版需要保证：

- 所有 Worker 返回同一种 RawItem。
- 主节点聚合后形成 NewsEvent。
- 榜单输出使用 LeaderboardItem。
- 每轮 Worker 运行形成 SourceRun。
- 调度状态形成 WorkerState。

## 2. 核心对象

### 2.1 RawItem

RawItem 是子节点返回给主节点的原始新闻项。

| 字段 | 说明 |
|---|---|
| `raw_id` | 原始项唯一标识，可由 source_id、url、published_at 等生成 |
| `source_type` | rss / github_release / github_trending / reddit |
| `source_id` | 信源配置中的唯一 ID |
| `source_name` | 人类可读信源名 |
| `worker_id` | 产生该项的 Worker |
| `title` | 原始标题 |
| `url` | 原始链接 |
| `canonical_url` | 主节点规范化后的链接，初始可为空 |
| `raw_text` | RSS 摘要、release notes、Reddit 标题等原始文本 |
| `published_at` | 原始发布时间 |
| `fetched_at` | 抓取时间 |
| `topics` | 主题标签 |
| `metadata` | 信源特有字段，如 GitHub stars、Reddit view_hits |

RawItem 不承担全局去重、最终排序和真假判断。

### 2.2 SourceRun

SourceRun 描述一次 Worker 运行。

| 字段 | 说明 |
|---|---|
| `run_id` | 本轮运行 ID |
| `worker_id` | Worker 名称 |
| `started_at` | 开始时间 |
| `finished_at` | 结束时间 |
| `status` | success / partial / failed |
| `items_count` | 返回 RawItem 数量 |
| `error_count` | 错误数量 |
| `error_summary` | 简要错误信息 |
| `duration_ms` | 耗时 |

### 2.3 NewsEvent

NewsEvent 是主节点把多个 RawItem 聚合后的新闻事件。

| 字段 | 说明 |
|---|---|
| `event_id` | 事件 ID |
| `canonical_title` | 主节点选择的代表标题 |
| `canonical_url` | 代表链接 |
| `summary_text` | 基于原始文本拼接或规则提取的摘要，第一版不使用 LLM |
| `topics` | 合并后的主题 |
| `source_count` | 命中的信源数量 |
| `sources` | 关联 RawItem 列表或引用 |
| `first_seen_at` | 系统首次发现时间 |
| `latest_seen_at` | 最近一次出现时间 |
| `published_at` | 代表发布时间 |
| `score` | 当前总分 |
| `score_breakdown` | 评分明细 |

### 2.4 LeaderboardItem

LeaderboardItem 是面向最终输出的榜单项。

| 字段 | 说明 |
|---|---|
| `rank` | 排名 |
| `event_id` | 对应 NewsEvent |
| `title` | 展示标题 |
| `url` | 展示链接 |
| `topics` | 主题 |
| `score` | 总分 |
| `source_count` | 信源数量 |
| `source_names` | 信源名列表 |
| `reason` | 上榜原因，例如“官方发布 + Reddit 热议” |
| `updated_at` | 榜单更新时间 |

### 2.5 WorkerState

WorkerState 描述调度器中的 Worker 状态。

| 字段 | 说明 |
|---|---|
| `worker_id` | Worker ID |
| `enabled` | 是否启用 |
| `next_due_at` | 下次运行时间 |
| `last_run_at` | 上次运行时间 |
| `last_success_at` | 上次成功时间 |
| `consecutive_failures` | 连续失败次数 |
| `last_error` | 最近错误 |
| `jitter_min_seconds` | 最小随机间隔 |
| `jitter_max_seconds` | 最大随机间隔 |

## 3. 对象生命周期

```text
Worker 采集
  ↓
RawItem 产生
  ↓
主节点保存 RawItem
  ↓
主节点规范化 URL / 标题
  ↓
主节点聚合为 NewsEvent
  ↓
主节点计算 score
  ↓
生成 LeaderboardItem
  ↓
导出榜单快照
```

## 4. 实现要求

| 要求 | 说明 |
|---|---|
| 字段稳定 | 第一版确定后避免频繁改字段名 |
| 可序列化 | 所有对象都能稳定转为 JSON |
| 可校验 | Worker 返回数据必须经过模型校验 |
| 可追溯 | LeaderboardItem 必须能回溯到 NewsEvent 和 RawItem |
| 可扩展 | metadata 允许保存信源特有信息 |

## 5. 测试验收

| 测试项 | 验收标准 |
|---|---|
| RawItem 校验 | 缺少 title/url/source_id 时应被标记为无效或拒绝入库 |
| SourceRun 记录 | Worker 成功、部分失败、完全失败都能产生 SourceRun |
| NewsEvent 关联 | 一个事件能关联多个 RawItem |
| JSON 导出 | 所有核心对象可导出为稳定 JSON |
| 时间字段 | 所有时间字段统一使用带时区 ISO 格式 |
| 向后兼容 | 新增字段不破坏旧数据读取 |
