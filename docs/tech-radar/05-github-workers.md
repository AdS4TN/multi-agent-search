# 05. GitHub Releases / Trending Worker

## 1. 模块目标

GitHub Worker 负责采集开源项目动态，包括重点仓库 releases 和趋势仓库发现。GitHub 数据用于补充开发者工具、开源模型、基础设施和安全工具方面的热点。

## 2. Worker 拆分

| Worker | 目标 |
|---|---|
| `github-releases` | 监控人工配置的重点仓库 release |
| `github-trending` | 使用 GitHub Search API 发现近期高关注仓库 |

两个 Worker 独立运行，避免 trending 搜索限流影响 releases 采集。

## 3. GitHub Releases Worker

### 3.1 职责

| 职责 | 说明 |
|---|---|
| 加载仓库配置 | 读取 owner/repo、topics、priority |
| 请求 releases | 获取最近 release 列表 |
| 时间过滤 | 只保留时间窗口内 release |
| 提取 release notes | 保存 title、body、tag、published_at |
| 转 RawItem | 将 release 转为统一 RawItem |
| 记录 rate limit | 保存 API 额度相关信息 |

### 3.2 重点字段

| GitHub 字段 | RawItem 字段 |
|---|---|
| repo full name | `source_name` |
| release name/tag | `title` |
| release html_url | `url` |
| release body | `raw_text` |
| published_at | `published_at` |
| stars/forks/topics | `metadata` |

## 4. GitHub Trending Worker

### 4.1 职责

GitHub 没有官方稳定的 Trending API，第一版使用 Search API 近似实现。

搜索维度建议包括：

| 主题 | 搜索方向 |
|---|---|
| LLM | large-language-model、llm、inference |
| AI Agent | ai-agent、agent-framework |
| Developer Tools | cli、devtools、productivity |
| Infra | database、observability、cloud-native |
| Security | security、vulnerability、supply-chain |

### 4.2 结果筛选

Trending Worker 可以做轻量确定性过滤：

| 过滤 | 说明 |
|---|---|
| 最小 stars | 过滤极低影响项目 |
| 最近 push | 只看近期活跃项目 |
| 主题匹配 | 匹配配置中的 topic |
| 每主题上限 | 控制返回数量 |

注意：这不是最终排序，只是避免过多噪声进入主节点。

## 5. 认证策略

| 方式 | 优先级 | 说明 |
|---|---:|---|
| `GITHUB_TOKEN` | 1 | 推荐配置，提高 rate limit |
| GitHub App token | 2 | 后续可选 |
| `gh auth token` | 3 | 本机已登录时可用 |
| 未认证 | 4 | 仅低频调试可用 |

第一版应允许未配置 token，但状态里必须明确提示 rate limit 风险。

## 6. 错误处理

| 错误 | 处理 |
|---|---|
| 403 rate limit | 记录 rate_limited，延长 Worker 下次运行间隔 |
| 404 repo not found | 记录源错误，建议人工检查配置 |
| 5xx | 可重试，失败后 partial |
| release body 为空 | 仍保留 release RawItem |
| Search API 无结果 | 视为成功，items 为空 |

## 7. 测试验收

| 测试项 | 验收标准 |
|---|---|
| Release 采集 | 能从样例 repo release 响应生成 RawItem |
| Trending 采集 | 能从 search 响应生成 RawItem |
| Token 可选 | 有 token 和无 token 均可运行 |
| Rate limit 记录 | 403 rate limit 能进入 SourceRun errors |
| 时间过滤 | 过旧 release 不进入结果 |
| Metadata 完整 | stars、forks、repo、tag 能进入 metadata |
| 部分失败 | 某个 repo 失败不影响其他 repo |
