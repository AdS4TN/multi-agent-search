# 08 - Observability：日志与观测模块

## 模块目标

让代理池更新、节点健康、Mihomo 运行状态、Reddit RSS 请求结果都可追踪。

## 日志文件建议

| 文件 | 内容 |
|---|---|
| proxy-source.log | 代理源拉取成功/失败 |
| aggregator-adapter.log | 解析与转换状态 |
| proxy-inventory.log | 节点去重、禁用、恢复 |
| health-check.log | 健康检查结果 |
| mihomo-runtime.log | Mihomo 启停状态 |
| reddit-rss-proxy.log | Reddit RSS 请求与冷却 |

## 核心指标

```text
proxy_sources_total
proxy_sources_enabled
nodes_parsed_total
nodes_healthy_total
mihomo_running
reddit_rss_success_total
reddit_rss_403_total
reddit_rss_429_total
reddit_rss_timeout_total
last_success_at
last_pool_refresh_at
```

## 日志脱敏

必须隐藏：

- 代理订阅 token。
- URL query 中的敏感参数。
- 任何账号、密码、Cookie。

## 验收标准

- 能从日志判断代理池是否更新成功。
- 能从日志判断 Reddit RSS 是否走了 7898。
- 错误日志能定位模块和失败原因。
