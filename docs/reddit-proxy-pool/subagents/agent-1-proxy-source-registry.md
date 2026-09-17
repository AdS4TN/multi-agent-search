# Agent 1 - Proxy Source Registry

## 角色

负责代理源登记模块设计。

## 目标

定义 `config/proxy-sources.json` 的结构、校验规则、状态更新规则。

## 输入文档

- `../01-proxy-source-registry.md`
- `../00-overview.md`

## 交付物

- 代理源配置字段说明
- 状态流转规则
- 校验规则
- 示例配置，不包含真实敏感 token

## 工作边界

不主动搜索代理源，不实现网络请求。

## 关键验收标准

- 可以表达 enabled/priority/trust_level/fail_count
- 能支持禁用和降权
- 日志脱敏规则明确

## 输出要求

- 使用中文。
- 不读取浏览器 Cookie、密码、系统凭据。
- 不修改与本模块无关的文件。
- 所有设计需要可被其他模块消费。
- 如发现上游设计不完整，在输出中明确列出阻塞点和建议。
