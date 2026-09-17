# 07. SQLite 存储与状态管理

## 1. 模块目标

存储模块负责保存系统运行中的所有关键状态和结果，使系统具备可恢复、可追溯、可调试能力。第一版使用 SQLite + WAL，避免额外部署数据库服务。

## 2. 存储范围

| 数据 | 是否持久化 | 说明 |
|---|---|---|
| RawItem | 是 | 原始新闻项 |
| SourceRun | 是 | Worker 运行记录 |
| WorkerState | 是 | 调度状态 |
| NewsEvent | 是 | 聚合后的新闻事件 |
| LeaderboardSnapshot | 是 | 榜单快照 |
| RSS cache | 是 | ETag / Last-Modified |
| 临时 HTTP 响应体 | 否 | 除非调试模式，不默认保存 |

## 3. 数据库建议

运行目录：

```text
D:\Temp\tech-radar-runtime\db\tech-radar.sqlite
```

启用 WAL：

| 设置 | 目的 |
|---|---|
| WAL mode | 提高读写并发和崩溃恢复能力 |
| busy timeout | 避免短暂锁冲突直接失败 |
| 定期 vacuum | 后续运维可选 |

## 4. 逻辑表设计

不在本文写具体建表代码，但逻辑上需要以下表：

| 表 | 用途 |
|---|---|
| `raw_items` | 保存所有 Worker 返回的原始项 |
| `source_runs` | 保存每次 Worker 运行记录 |
| `worker_state` | 保存调度状态 |
| `news_events` | 保存聚合事件 |
| `event_sources` | 保存 NewsEvent 与 RawItem 的关联 |
| `leaderboard_snapshots` | 保存每次榜单结果 |
| `source_cache` | 保存 RSS/GitHub 条件请求缓存 |
| `system_kv` | 保存系统版本、迁移状态等小型配置 |

## 5. 写入原则

| 原则 | 说明 |
|---|---|
| 先原始后聚合 | RawItem 入库后再生成 NewsEvent |
| SourceRun 全记录 | 成功和失败运行都要记录 |
| 榜单快照不可变 | 每次生成新的 snapshot，不直接覆盖历史 |
| 当前榜单可指针化 | 用 current 标记或 system_kv 指向最新 snapshot |
| 错误不丢失 | Worker 错误要能在状态中看到 |

## 6. 去重相关索引

为了支持主节点去重，应为以下字段建立查询能力：

| 字段 | 用途 |
|---|---|
| canonical_url | URL 去重 |
| normalized_title | 标题相似度候选检索 |
| published_at | 时间窗口聚合 |
| source_id | 同源排查 |
| topic | 榜单分区和过滤 |

## 7. 数据保留策略

第一版建议：

| 数据 | 保留时间 |
|---|---|
| RawItem | 30~90 天 |
| SourceRun | 30 天 |
| NewsEvent | 90 天 |
| LeaderboardSnapshot | 30 天 |
| 错误日志 | 30 天 |

后续可增加归档和清理命令。

## 8. 测试验收

| 测试项 | 验收标准 |
|---|---|
| 初始化 | 首次运行能创建数据库和必要结构 |
| WAL | 数据库启用 WAL，不因读写冲突轻易失败 |
| RawItem 入库 | 合法 RawItem 能保存并读取 |
| SourceRun 入库 | 成功/失败运行均能保存 |
| 重启恢复 | 进程重启后 WorkerState 不丢失 |
| 榜单快照 | 每次榜单生成都有独立 snapshot |
| 查询性能 | 在万级 RawItem 下状态和榜单查询仍可接受 |
