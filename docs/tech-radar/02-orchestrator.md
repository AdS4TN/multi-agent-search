# 02. 主节点 Orchestrator

## 1. 模块目标

主节点是系统唯一的调度和决策中心。它不直接处理某个信源的抓取细节，而是通过 Worker 协议调度各子节点，并统一完成数据入库、去重、聚合、评分和榜单更新。

## 2. 职责范围

主节点负责：

| 职责 | 说明 |
|---|---|
| Worker 调度 | 根据 WorkerState 判断哪些 Worker 到期 |
| 运行隔离 | 单个 Worker 失败不影响其他 Worker |
| 结果接收 | 接收 WorkerResult 和 RawItem |
| 数据入库 | 保存 RawItem、SourceRun 和 WorkerState |
| 全局去重 | 对所有 RawItem 做统一去重 |
| 事件聚合 | 将多条 RawItem 合并为 NewsEvent |
| 排序更新 | 计算分数并生成 LeaderboardItem |
| 输出导出 | 生成当前榜单 JSON / Markdown |

主节点不负责：

| 非职责 | 说明 |
|---|---|
| 具体网页解析 | 交给对应 Worker |
| Reddit 代理管理 | 交给 reddit_proxy_pool |
| 搜索扩展 | 第一版不做 |
| 真假判断 | 第一版不做 |
| LLM 摘要 | 第一版不做 |

## 3. 调度策略

主节点采用轮询式调度：

```text
加载 WorkerState
  ↓
筛选 next_due_at <= now 的 Worker
  ↓
按优先级和到期时间排序
  ↓
逐个运行 Worker
  ↓
保存结果
  ↓
更新下一次运行时间
```

调度要求：

| 要求 | 说明 |
|---|---|
| 随机间隔 | Worker 运行完成后使用 jitter 生成下次运行时间 |
| 失败退避 | 连续失败时延长下次运行间隔 |
| 可暂停 | 配置中 disabled 的 Worker 不运行 |
| 可恢复 | 进程重启后从 SQLite 恢复状态 |
| Reddit 特例 | Reddit Worker 继续服从 reddit_proxy_pool 的限速和冷却 |

## 4. 主节点运行模式

| 模式 | 说明 |
|---|---|
| run-once | 执行一轮到期 Worker，适合调试和定时任务 |
| daemon | 常驻运行，周期性检查到期 Worker |
| status | 查看 Worker 状态、最近错误和榜单状态 |
| rebuild | 从 RawItem 重建 NewsEvent 和榜单，适合调参 |
| export | 导出 JSON / Markdown |

## 5. 错误处理

| 错误类型 | 处理方式 |
|---|---|
| 单个 Worker 异常 | 记录 SourceRun failed，更新 WorkerState，不中断主节点 |
| Worker 返回部分无效数据 | 有效项入库，无效项记录错误数量 |
| 存储写入失败 | 当前轮终止，避免状态不一致 |
| 排序失败 | 保留上一版榜单，记录错误 |
| Reddit 冷却 | 本轮跳过 Reddit Worker，不视为系统失败 |

## 6. 状态更新原则

- Worker 运行开始时写入 SourceRun started。
- Worker 完成后写入 SourceRun finished。
- RawItem 入库成功后再更新 WorkerState。
- 榜单生成成功后再更新 leaderboard snapshot。
- 失败时保留上一轮有效榜单。

## 7. 测试验收

| 测试项 | 验收标准 |
|---|---|
| 到期筛选 | 只运行 next_due_at 已到期且 enabled 的 Worker |
| 失败隔离 | 一个 Worker 抛错后，其他 Worker 仍可运行 |
| 状态恢复 | 删除进程后重启，能继续使用上次 WorkerState |
| run-once | 能完成一轮到期 Worker 调度并退出 |
| daemon | 能按轮询间隔持续运行，不重复高频执行同一 Worker |
| 榜单保护 | 新一轮排序失败时，不覆盖上一版可用榜单 |
| Reddit 跳过 | Reddit 冷却期间主节点能正确跳过并记录原因 |
