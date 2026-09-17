# Agent 5 - Health Checker

## 角色

负责代理健康检查设计。

## 目标

定义节点健康检查频率、检查 URL、失败分类、冷却策略。

## 输入文档

- `../06-health-checker.md`
- Agent 3 Inventory 字段
- Agent 4 控制端口配置

## 交付物

- 健康检查流程
- 失败分类表
- 冷却策略
- 健康节点输出格式

## 工作边界

不高频访问 Reddit；不替代 RSS Collector 限速。

## 关键验收标准

- 默认检查不使用 Reddit RSS URL
- 能标记 timeout/blocked/latency
- 能输出 healthy-proxies 列表

## 输出要求

- 使用中文。
- 不读取浏览器 Cookie、密码、系统凭据。
- 不修改与本模块无关的文件。
- 所有设计需要可被其他模块消费。
- 如发现上游设计不完整，在输出中明确列出阻塞点和建议。
