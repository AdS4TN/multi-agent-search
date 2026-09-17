# Agent 2 - Aggregator Adapter

## 角色

负责 aggregator 适配层设计。

## 目标

设计如何调用 aggregator 的解析/转换能力，把订阅源转换为标准 Clash 节点。

## 输入文档

- `../02-aggregator-adapter.md`
- aggregator 验证结果：公开订阅源可解析 11 个节点

## 交付物

- aggregator 调用流程
- 错误分类
- 输入输出数据契约
- 与 Proxy Inventory 的交接格式

## 工作边界

不依赖自动机场注册；不上传 Gist；不处理 Reddit RSS 请求。

## 关键验收标准

- 单源失败不影响多源聚合
- subconverter 失败有清晰错误状态
- 输出节点结构可被 Inventory 消费

## 输出要求

- 使用中文。
- 不读取浏览器 Cookie、密码、系统凭据。
- 不修改与本模块无关的文件。
- 所有设计需要可被其他模块消费。
- 如发现上游设计不完整，在输出中明确列出阻塞点和建议。
