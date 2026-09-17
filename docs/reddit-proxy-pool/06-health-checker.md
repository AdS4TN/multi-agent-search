# 06 - Health Checker：代理健康检查模块

## 模块目标

对代理节点进行低成本活性检查，筛选可用于 Reddit 代理池的节点。

## 职责

- 调用 Mihomo 控制接口检查节点延迟。
- 更新 Proxy Inventory 中的健康状态。
- 输出健康节点列表。
- 记录失败原因。

## 输入

```text
Proxy Inventory 节点列表
Mihomo 控制端口
健康检查策略
```

## 输出

```text
healthy-proxies.json
health-check.log
```

## 检查策略

基础检查使用轻量 URL：

```text
https://www.google.com/generate_204
```

Reddit 可达性检查必须低频，不作为每轮健康检查默认项。

## 失败分级

| 类型 | 含义 |
|---|---|
| timeout | 代理超时 |
| controller_error | Mihomo 控制接口异常 |
| bad_delay | 延迟过高或 delay 返回异常 |
| reddit_blocked | Reddit 返回 403/429，需单独冷却 |

## 冷却建议

| 情况 | 节点处理 |
|---|---|
| 单次 timeout | fail_count +1 |
| 连续失败 3 次 | 暂时禁用 |
| Reddit 403 | 对 reddit.com 标记 blocked，冷却 30-60 分钟 |
| Reddit 429 | 冷却 10-30 分钟 |

## 验收标准

- 能识别至少一个可用节点。
- 健康检查不会频繁访问 Reddit。
- 健康节点能被 Config Builder 使用。
