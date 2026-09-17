# 10. 导出、日志与可观测性

## 1. 模块目标

导出与可观测性模块负责让系统运行结果和运行状态可查看、可追溯、可排查。第一版重点支持 JSON、Markdown、状态摘要和错误日志。

## 2. 输出目录

建议运行时目录：

```text
D:\Temp\tech-radar-runtime
```

目录结构：

```text
D:\Temp\tech-radar-runtime
  db\
  logs\
  runs\
  leaderboard\
  exports\
```

## 3. 榜单导出

| 格式 | 用途 |
|---|---|
| JSON | 程序消费、后续 Web Dashboard 使用 |
| Markdown | 人类阅读、复制到日报或笔记 |

JSON 导出应包含：

| 内容 | 说明 |
|---|---|
| generated_at | 生成时间 |
| leaderboard_version | 榜单版本或 snapshot ID |
| items | 榜单项 |
| score_breakdown | 分数明细 |
| sources | 每个事件关联来源 |

Markdown 导出应包含：

| 内容 | 说明 |
|---|---|
| 今日总榜 | Top N |
| 分主题榜 | AI、GitHub、安全等 |
| 每条上榜原因 | 简短规则化说明 |
| 来源链接 | 保留主要来源 |

## 4. 日志要求

| 日志 | 说明 |
|---|---|
| 主节点运行日志 | 调度、状态、榜单更新 |
| Worker 运行日志 | 请求数、成功数、失败数 |
| 错误日志 | 异常栈、source_id、worker_id |
| 性能日志 | Worker 耗时、排序耗时 |

日志必须注意：

- 不输出订阅 token。
- 不输出代理节点敏感配置。
- 不输出 GitHub token。
- URL 中的 token/query secret 需要脱敏。

## 5. 状态查看

状态命令应展示：

| 信息 | 说明 |
|---|---|
| Worker 列表 | enabled、next_due_at、last_success_at |
| 最近失败 | worker_id、source_id、错误摘要 |
| 当前榜单 | snapshot ID、生成时间、条目数 |
| 数据规模 | RawItem 数、NewsEvent 数 |
| Reddit 状态 | 是否冷却、最近运行摘要 |

## 6. 运行报告

每次 run-once 或 daemon 周期可以生成简短运行报告：

| 字段 | 说明 |
|---|---|
| started_at / finished_at | 运行时间 |
| workers_run | 本轮运行 Worker |
| items_ingested | 入库 RawItem 数 |
| events_updated | 更新事件数 |
| leaderboard_updated | 是否更新榜单 |
| errors | 错误摘要 |

## 7. 测试验收

| 测试项 | 验收标准 |
|---|---|
| JSON 导出 | 输出结构稳定，可被重新读取 |
| Markdown 导出 | 人类可读，包含标题、链接、来源、上榜原因 |
| 状态命令 | 能展示 Worker 状态和最近错误 |
| 敏感信息脱敏 | token、secret 不出现在日志和导出中 |
| 错误可定位 | 错误日志包含 worker_id 和 source_id |
| 历史快照 | 能查看最新和历史榜单文件 |
