# 00 - 总体架构与边界

## 目标

将已验证的临时流程整理成一个可重复运行、可监控、可接入 Reddit RSS Collector 的正式 `reddit-proxy-pool`。

## 已验证事实

```text
测试仓库：D:\Temp\wzdnzd-aggregator
测试订阅源：https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub
解析节点数：11
活性可用数：3
临时入口端口：127.0.0.1:7898
控制端口：127.0.0.1:9098
Reddit RSS 测试：https://www.reddit.com/r/artificial/.rss
结果：HTTP 200，application/atom+xml; charset=UTF-8
```

## 总体架构

```text
config/proxy-sources.json
  ↓
Proxy Source Registry
  ↓
Aggregator Adapter
  ↓
Proxy Inventory
  ↓
Health Checker
  ↓
Mihomo Config Builder
  ↓
Mihomo Runtime Manager
  ↓
127.0.0.1:7898
  ↓
Reddit RSS Collector
```

## 技术栈

| 层级 | 技术选择 |
|---|---|
| 代理订阅解析 | wzdnzd/aggregator |
| 协议转换 | subconverter |
| 代理运行时 | Mihomo / Clash Meta |
| 配置格式 | YAML / JSON |
| 状态存储 | MVP 使用 JSON，稳定后可切 SQLite |
| 调度 | Windows Task Scheduler，后续可接 cron |
| 采集端 | Python RSS Collector |
| 本地代理端口 | `127.0.0.1:7898` |
| 控制端口 | `127.0.0.1:9098` |

## 非目标

- 不实现自研 VMess/VLESS/Trojan/Hysteria 协议客户端。
- 不读取浏览器 Cookie。
- 不把 Reddit 403/429 作为“立刻换代理重试”的信号。
- 不让普通 RSS 或浏览器流量共用 Reddit 专用端口。
- 不依赖 aggregator 的自动机场注册作为正式主路径。

## 关键原则

1. **隔离端口**：Reddit RSS 固定走 `7898`，不污染系统代理。
2. **可控代理源**：代理订阅源由我们维护，不交给 Agent 自由发现。
3. **低频请求**：代理池只提供出口，不替代 Reddit RSS 限速。
4. **失败冷却**：403/429 后暂停，不连续打。
5. **可观测**：每次代理更新、健康检查、RSS 请求都有日志。
