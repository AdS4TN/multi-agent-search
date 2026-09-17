# 02 - Aggregator Adapter：Aggregator 适配模块

## 模块目标

封装 `wzdnzd/aggregator` 的代理解析与转换能力，将代理订阅源转换为标准 Clash 节点。

## 职责

- 接收 Proxy Source Registry 输出的代理源列表。
- 拉取订阅内容。
- 调用 aggregator/subconverter 解析节点。
- 聚合多个订阅源的节点。
- 将失败源与成功源分开记录。

## 输入

```text
启用代理源列表
aggregator 工作目录
subconverter 可执行文件路径
```

## 输出

```text
标准 Clash 节点列表
源级运行报告
```

## 设计约束

- 不直接依赖 `collect.py` 的自动机场注册流程作为主路径。
- 不要求 Gist token。
- 不上传任何远程存储。
- 所有输出先落本地 runtime/generated。

## aggregator 使用策略

优先复用以下能力：

```text
AirPort.decode()
subconverter.generate_conf()
subconverter.convert()
clash.filter_proxies()
```

不推荐在 MVP 阶段依赖：

```text
collect.py 自动注册机场
GitHub Gist 上传
自动邮件注册
大规模并发扫描
```

## 错误处理

| 场景 | 处理 |
|---|---|
| 订阅源超时 | 标记该源失败，继续下一个源 |
| 解析为空 | 标记 empty_result |
| subconverter 失败 | 保存原始片段与错误摘要 |
| 节点格式异常 | 丢弃异常节点，保留其他节点 |

## 验收标准

- 给定一个公开订阅源，可以解析出非空节点列表。
- 多个订阅源中一个失败不影响其他源。
- 生成的节点能被 Mihomo 配置生成模块消费。
- 日志中不泄露完整订阅 token。
