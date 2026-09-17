# 03 - Proxy Inventory：代理节点清单模块

## 模块目标

维护代理节点清单，完成去重、基础过滤、状态记录。

## 职责

- 接收 Aggregator Adapter 输出的 Clash 节点。
- 根据 server、port、type、uuid 等信息去重。
- 维护节点状态。
- 为 Health Checker 和 Config Builder 提供节点列表。

## 输入

```text
标准 Clash 节点列表
代理源元数据
历史节点状态
```

## 输出

```text
proxy-inventory.json 或 proxy-inventory.db
可参与健康检查的节点列表
```

## 推荐节点字段

| 字段 | 说明 |
|---|---|
| node_id | 节点唯一 ID |
| source_id | 来源 ID |
| name | 节点名称 |
| type | 协议类型 |
| server | 服务器地址 |
| port | 端口 |
| alive | 最近是否可用 |
| latency_ms | 最近延迟 |
| success_count | 成功次数 |
| fail_count | 连续失败次数 |
| first_seen_at | 首次出现时间 |
| last_seen_at | 最近出现时间 |
| last_checked_at | 最近检查时间 |
| disabled | 是否禁用 |

## 去重原则

优先以真实连接信息去重，而不是只看节点名称。

建议组合：

```text
type + server + port + uuid/password/cipher/sni
```

## 过滤原则

MVP 阶段只做基础过滤：

- 缺少 server 或 port 的节点丢弃。
- 不支持的协议丢弃。
- 明显私网地址按策略丢弃。
- disabled 节点不进入配置生成。

## 验收标准

- 相同节点不会重复进入 Mihomo 配置。
- 每个节点有稳定 node_id。
- 可追踪节点来自哪个代理源。
