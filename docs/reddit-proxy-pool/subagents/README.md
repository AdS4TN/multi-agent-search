# Subagent 任务书索引

本目录用于把 reddit-proxy-pool 拆分成可交给多个 subagent 并行完成的任务包。

> 当前 Codex 工具环境未提供真实 subagent 调用接口；这些任务书可作为后续派发给独立 agent 的标准输入。

## 推荐执行顺序

```text
Agent 0 架构协调
  ↓
Agent 1 Proxy Source Registry
Agent 2 Aggregator Adapter
Agent 3 Proxy Inventory
  ↓
Agent 4 Mihomo Config Builder
Agent 5 Health Checker
Agent 6 Mihomo Runtime Manager
  ↓
Agent 7 Reddit RSS Policy
Agent 8 Observability & Operations
  ↓
Agent 9 Acceptance Review
```

## 任务文件

| Agent | 任务书 |
|---|---|
| Agent 0 | [agent-0-coordinator.md](./agent-0-coordinator.md) |
| Agent 1 | [agent-1-proxy-source-registry.md](./agent-1-proxy-source-registry.md) |
| Agent 2 | [agent-2-aggregator-adapter.md](./agent-2-aggregator-adapter.md) |
| Agent 3 | [agent-3-proxy-inventory.md](./agent-3-proxy-inventory.md) |
| Agent 4 | [agent-4-mihomo-config-builder.md](./agent-4-mihomo-config-builder.md) |
| Agent 5 | [agent-5-health-checker.md](./agent-5-health-checker.md) |
| Agent 6 | [agent-6-runtime-manager.md](./agent-6-runtime-manager.md) |
| Agent 7 | [agent-7-reddit-rss-policy.md](./agent-7-reddit-rss-policy.md) |
| Agent 8 | [agent-8-observability-operations.md](./agent-8-observability-operations.md) |
| Agent 9 | [agent-9-acceptance-review.md](./agent-9-acceptance-review.md) |
