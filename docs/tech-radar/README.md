# Tech Radar 开发文档索引

本文档集用于设计第一版科技新闻采集与榜单工具。第一版不接入 X/Twitter，不做搜索扩展节点，不使用 LLM Agent；系统由一个主节点统一调度多个确定性 Worker，最终由主节点完成去重、聚合、排序和榜单更新。

## 第一版目标

构建一个本地可运行、可恢复、可观测的科技新闻雷达工具：

| 能力 | 说明 |
|---|---|
| 多信源采集 | RSS、GitHub Releases、GitHub Trending、Reddit RSS |
| Worker 工程化 | 子节点只负责确定性采集、解析和轻量过滤 |
| 主节点集中决策 | 去重、聚合、评分、排序、榜单更新全部由主节点完成 |
| 本地持久化 | 使用 SQLite 保存原始新闻、运行状态、聚合事件和榜单快照 |
| 可解释排序 | 用规则评分，避免第一版引入不可控 LLM 判断 |
| 可运维 | 支持状态查看、失败记录、随机调度间隔、Markdown/JSON 导出 |

## 文档结构

| 编号 | 文档 | 模块 |
|---|---|---|
| 00 | [00-overview.md](./00-overview.md) | 总体架构与边界 |
| 01 | [01-data-model.md](./01-data-model.md) | 数据模型与对象生命周期 |
| 02 | [02-orchestrator.md](./02-orchestrator.md) | 主节点 Orchestrator |
| 03 | [03-worker-contract.md](./03-worker-contract.md) | Worker 通用协议 |
| 04 | [04-rss-workers.md](./04-rss-workers.md) | RSS 分片 Worker |
| 05 | [05-github-workers.md](./05-github-workers.md) | GitHub Releases / Trending Worker |
| 06 | [06-reddit-worker.md](./06-reddit-worker.md) | Reddit RSS Worker 适配 |
| 07 | [07-storage-state.md](./07-storage-state.md) | SQLite 存储与状态管理 |
| 08 | [08-dedup-aggregation.md](./08-dedup-aggregation.md) | 主节点去重与事件聚合 |
| 09 | [09-ranking-leaderboard.md](./09-ranking-leaderboard.md) | 评分排序与榜单生成 |
| 10 | [10-export-observability.md](./10-export-observability.md) | 导出、日志与可观测性 |
| 11 | [11-operations.md](./11-operations.md) | 调度、运行与运维策略 |
| 12 | [12-testing-acceptance.md](./12-testing-acceptance.md) | 测试矩阵与验收标准 |

## 第一版明确不做

| 暂不实现项 | 原因 |
|---|---|
| X/Twitter 采集 | API 成本和稳定性问题较大，后续作为可选增强 |
| Tavily/Grok 搜索扩展节点 | 第一版先保证基础采集、去重和排序稳定 |
| LLM 事实核验 / 谣言判断 | 容易引入不可解释误判，后续单独设计 |
| 分布式队列 | 本地工具阶段不需要 Redis/Celery/Kafka |
| Web Dashboard | 第一版先输出 JSON/Markdown，可后续扩展 |
| embedding 去重 | 第一版使用 URL 和标题相似度即可 |

## 推荐技术栈

| 层级 | 选型 |
|---|---|
| 主语言 | Python 3.12 |
| 架构 | 模块化单体 + 插件式 Worker |
| 调度 | 主节点自研轻量调度 + SQLite 持久化状态 |
| HTTP | httpx |
| RSS 解析 | feedparser |
| 数据模型 | Pydantic v2 |
| 存储 | SQLite + WAL |
| 去重 | URL 规范化 + 标题相似度 |
| 排序 | 规则评分 |
| CLI | argparse |
| 输出 | JSON + Markdown |
| 测试 | pytest + HTTP mock |

## 里程碑

| 阶段 | 目标 | 可验收产物 |
|---|---|---|
| M1 | 建立数据模型、存储和 Worker 协议 | 可导入样例 RawItem 并保存 |
| M2 | 接入 RSS 分片 Worker | 可采集多组 RSS 并入库 |
| M3 | 接入 GitHub Worker | 可采集 releases 和 trending |
| M4 | 接入 Reddit Worker | 可读取 reddit_proxy_pool 输出并转换为 RawItem |
| M5 | 主节点去重、聚合、排序 | 可生成 NewsEvent 和 leaderboard |
| M6 | 导出和运维能力 | 可查看状态、导出 JSON/Markdown、恢复运行 |
