# 04. RSS 分片 Worker

## 1. 模块目标

RSS 分片 Worker 负责采集 RSS / Atom 信源，并转换为统一 RawItem。由于 RSS 源数量较多，第一版按来源性质拆成多个 Worker，降低单个 Worker 的复杂度和失败影响面。

## 2. Worker 拆分

| Worker | 范围 | 示例 |
|---|---|---|
| `rss-official` | 官方博客、公司博客 | OpenAI Blog、Anthropic、Google AI、Hugging Face |
| `rss-media` | 科技媒体 | Ars Technica、The Verge、TechCrunch、MIT Tech Review |
| `rss-ai` | AI/LLM 博客和研究作者 | Simon Willison、Sebastian Raschka、Lilian Weng |
| `rss-engineering` | 工程、安全、开源基础设施 | 安全博客、DevOps、开源工程博客 |

拆分原则：

- 一个 Worker 控制在可管理的源数量内。
- 同类信源使用相近的刷新频率。
- 某类 RSS 失败不影响其他 RSS 类别。

## 3. 实现职责

RSS Worker 需要实现：

| 职责 | 说明 |
|---|---|
| 加载源配置 | 读取该分片对应的 RSS 源列表 |
| 条件请求 | 支持 ETag / Last-Modified 缓存 |
| HTTP 请求 | 统一 User-Agent、超时、重试和错误记录 |
| Feed 解析 | 支持 RSS 和 Atom |
| 时间过滤 | 只返回指定时间窗口内的内容 |
| RawItem 转换 | 标题、链接、摘要、发布时间、topics 标准化 |
| 运行统计 | 返回请求数、成功数、失败数、解析数量 |

## 4. 字段映射

| RSS 字段 | RawItem 字段 |
|---|---|
| feed source id | `source_id` |
| feed title/name | `source_name` |
| entry title | `title` |
| entry link | `url` |
| summary/content | `raw_text` |
| published/updated | `published_at` |
| fetch time | `fetched_at` |
| source topics | `topics` |

## 5. 缓存策略

RSS Worker 应维护源级缓存：

| 缓存项 | 用途 |
|---|---|
| ETag | 减少未更新 feed 的传输 |
| Last-Modified | 支持条件请求 |
| last_success_at | 判断源是否长期失败 |
| last_error | 运维定位 |

缓存应放入 SQLite 或运行时状态目录，不能只存在内存中。

## 6. 刷新频率建议

| 分片 | 建议间隔 |
|---|---|
| rss-official | 20~40 分钟 |
| rss-media | 30~60 分钟 |
| rss-ai | 45~90 分钟 |
| rss-engineering | 60~120 分钟 |

间隔由主节点生成 jitter，Worker 本身不决定下一次运行时间。

## 7. 错误处理

| 错误 | 处理 |
|---|---|
| 单源超时 | 记录该源错误，继续其他源 |
| 解析失败 | 记录 parse_error，可尝试基础 XML 解析降级 |
| 304 Not Modified | 视为成功，但不产生新 RawItem |
| 404/410 | 记录源失效，后续可人工禁用 |
| 429/403 | 记录限流或拒绝，不立即高频重试 |

## 8. 测试验收

| 测试项 | 验收标准 |
|---|---|
| RSS 解析 | 能解析标准 RSS 2.0 feed |
| Atom 解析 | 能解析 Atom feed |
| 条件请求 | 第二次请求能带上 ETag / Last-Modified |
| 304 处理 | 304 不视为失败，不产生重复条目 |
| 部分失败 | 一个 feed 失败不影响同 Worker 内其他 feed |
| 时间过滤 | 过旧内容不会进入 RawItem |
| 字段完整 | 每条 RawItem 至少包含 source_id、title、url、fetched_at |
| 分片隔离 | rss-media 失败不影响 rss-official 的调度和结果 |
