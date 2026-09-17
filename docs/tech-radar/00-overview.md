# 00. 总体架构与边界

## 1. 系统定位

Tech Radar 是一个本地运行的科技新闻采集与榜单工具。它面向“今日热点科技新闻”的持续采集、整理和排序，不追求第一版就做到全自动事实判断。

第一版系统的核心原则是：

| 原则 | 说明 |
|---|---|
| 采集确定性 | 子节点使用确定性 Worker，不使用 LLM Agent 自主抓取 |
| 决策集中化 | 去重、聚合、排序统一在主节点完成 |
| 信源可解释 | 每条榜单新闻都能回溯到原始来源 |
| 运行可恢复 | 调度状态、失败状态和榜单快照需要持久化 |
| 先稳后强 | 第一版不接 X、不做搜索扩展、不做谣言判断 |

## 2. 逻辑架构

系统由一个主节点和多类 Worker 组成：

```text
Tech Radar Orchestrator
  ├─ RSS 官方/博客 Worker
  ├─ RSS 科技媒体 Worker
  ├─ RSS AI/LLM Worker
  ├─ RSS 安全/工程 Worker
  ├─ GitHub Releases Worker
  ├─ GitHub Trending Worker
  └─ Reddit RSS Worker
```

Worker 返回原始新闻项，主节点负责：

```text
接收 RawItem
  ↓
保存原始记录
  ↓
全局去重
  ↓
事件聚合
  ↓
规则评分
  ↓
更新榜单
  ↓
导出 JSON / Markdown
```

## 3. 第一版信源范围

| 信源 | 是否启用 | 说明 |
|---|---|---|
| RSS 官方博客 | 是 | OpenAI、Anthropic、Google AI、Hugging Face 等 |
| RSS 科技媒体 | 是 | Ars Technica、The Verge、TechCrunch 等 |
| RSS 个人/研究博客 | 是 | Simon Willison、Sebastian Raschka 等 |
| GitHub Releases | 是 | 重点开源项目版本发布 |
| GitHub Trending | 是 | 通过 GitHub Search API 近似发现趋势项目 |
| Reddit RSS | 是 | 复用 reddit_proxy_pool 的四路视角采集 |
| X/Twitter | 否 | 暂不接入 |
| Tavily/Grok 搜索 | 否 | 暂不接入 |

## 4. 运行形态

第一版推荐为本地 CLI 工具：

| 命令能力 | 说明 |
|---|---|
| 单轮运行 | 手动触发所有到期 Worker |
| 常驻运行 | 主节点循环调度 Worker |
| 状态查看 | 展示 Worker 状态、失败信息、下次运行时间 |
| 榜单查看 | 输出当前榜单摘要 |
| 导出 | 导出 JSON / Markdown |

运行数据放在 D 盘运行时目录，避免 C 盘空间压力：

```text
D:\Temp\tech-radar-runtime
```

## 5. 边界与非目标

第一版不解决以下问题：

| 非目标 | 说明 |
|---|---|
| 自动事实核验 | 不判断真假，不标记谣言 |
| 内容补充搜索 | 不调用 Tavily/Grok 扩展搜索 |
| 实时 Web 前端 | 先用 CLI 和文件输出 |
| 多用户权限 | 本地工具阶段不涉及用户系统 |
| 分布式部署 | 不引入 Redis/Celery/Kafka |
| 全文抓取 | 第一版以 RSS/API 返回内容为主，不强抓全文 |

## 6. 核心质量指标

| 指标 | 目标 |
|---|---|
| 可用性 | 单个 Worker 失败不影响其他 Worker |
| 可恢复性 | 进程重启后能从 SQLite 状态恢复 |
| 可解释性 | 榜单项能看到来源、命中信源、评分构成 |
| 去重质量 | 同一新闻多源报道应合并为一个事件 |
| 调度安全 | Reddit 请求必须继续遵守专用限频策略 |
| 输出稳定 | 每轮运行都能生成结构一致的 JSON / Markdown |

## 7. 开发顺序

推荐顺序：

1. 数据模型与存储。
2. Worker 通用协议。
3. RSS Worker。
4. GitHub Worker。
5. Reddit Worker 适配。
6. 主节点去重聚合。
7. 榜单评分。
8. 导出和状态查看。
9. 测试与运行文档。

该顺序的核心思想是：先让数据稳定进入系统，再做复杂排序。
