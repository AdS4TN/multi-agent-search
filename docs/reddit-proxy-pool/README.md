# Reddit Proxy Pool 开发文档索引

本文档集用于把临时验证过的 `aggregator + Mihomo + 7898` 方案整理成正式的 Reddit RSS 专用代理池。

## 目标链路

```text
Reddit RSS Collector
  ↓ http://127.0.0.1:7898
Reddit 专用 Mihomo 实例
  ↓ REDDIT-POOL
代理订阅源解析出的可用节点
  ↓
reddit.com / old.reddit.com / redd.it
```

## 模块清单

| 编号 | 文档 | 模块 |
|---|---|---|
| 00 | [00-overview.md](./00-overview.md) | 总体架构与边界 |
| 01 | [01-proxy-source-registry.md](./01-proxy-source-registry.md) | 代理源登记模块 |
| 02 | [02-aggregator-adapter.md](./02-aggregator-adapter.md) | Aggregator 适配模块 |
| 03 | [03-proxy-inventory.md](./03-proxy-inventory.md) | 代理节点清单模块 |
| 04 | [04-mihomo-config-builder.md](./04-mihomo-config-builder.md) | Mihomo 配置生成模块 |
| 05 | [05-mihomo-runtime-manager.md](./05-mihomo-runtime-manager.md) | Mihomo 运行时管理模块 |
| 06 | [06-health-checker.md](./06-health-checker.md) | 健康检查模块 |
| 07 | [07-reddit-rss-policy.md](./07-reddit-rss-policy.md) | Reddit RSS 请求策略模块 |
| 08 | [08-observability.md](./08-observability.md) | 日志与观测模块 |
| 09 | [09-scheduler-operations.md](./09-scheduler-operations.md) | 调度与运维模块 |
| 10 | [10-acceptance.md](./10-acceptance.md) | 验收标准与测试矩阵 |
| 11 | [11-mvp-usage.md](./11-mvp-usage.md) | MVP 使用说明 |
| 12 | [reddit-rss-four-view-collection.md](./12-reddit-rss-four-view-collection.md) | Reddit RSS 四路视角采集方法 |
| 13 | [13-reddit-monitor-usage.md](./13-reddit-monitor-usage.md) | Reddit Monitor 使用说明 |

## Subagent 任务书

见 [subagents/README.md](./subagents/README.md)。

> 当前 Codex 工具环境没有真实的 subagent 派发接口；本目录下的 subagent 任务书可以直接复制给独立 agent 执行，或由后续自动化调度器读取。
