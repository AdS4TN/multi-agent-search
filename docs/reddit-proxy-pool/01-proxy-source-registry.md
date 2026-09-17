# 01 - Proxy Source Registry：代理源登记模块

## 模块目标

维护代理订阅源列表，提供给 Aggregator Adapter 作为输入。

## 职责

- 保存代理订阅源元数据。
- 标记启用/禁用状态。
- 记录来源健康状态。
- 支持后续按优先级选择代理源。

## 输入

人工维护的代理源配置，建议文件：

```text
config/proxy-sources.json
```

## 输出

传给 Aggregator Adapter 的启用代理源列表。

## 推荐字段

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 稳定唯一 ID |
| name | string | 来源名称 |
| url | string | 订阅地址 |
| enabled | boolean | 是否启用 |
| priority | number | 优先级，数值越高越优先 |
| format_hint | string | clash / v2ray / mixed / unknown |
| trust_level | string | high / medium / low |
| note | string | 人工备注 |
| last_success_at | string | 最近拉取成功时间 |
| last_failed_at | string | 最近失败时间 |
| fail_count | number | 连续失败次数 |

## 错误处理

| 场景 | 处理 |
|---|---|
| URL 为空 | 跳过并记录配置错误 |
| enabled=false | 不传给后续模块 |
| 连续失败过多 | 自动降权或进入 disabled_candidates |
| 订阅源返回 404 | 标记失败，不立即删除 |

## 验收标准

- 能列出所有启用代理源。
- 能过滤无效 URL。
- 能记录成功/失败时间。
- 不把代理订阅 token 明文打印到日志。
