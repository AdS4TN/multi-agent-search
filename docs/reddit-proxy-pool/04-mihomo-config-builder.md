# 04 - Mihomo Config Builder：Reddit 配置生成模块

## 模块目标

根据健康节点生成 Reddit 专用 Mihomo 配置，固定暴露 `127.0.0.1:7898`。

## 职责

- 读取可用代理节点。
- 生成 Mihomo YAML 配置。
- 设置 Reddit 专用代理组 `REDDIT-POOL`。
- 设置本地端口与控制端口。
- 输出可直接启动的配置文件。

## 输入

```text
健康节点列表
端口配置
代理组策略
```

## 输出

```text
runtime/generated/reddit-pool.yaml
```

## 推荐配置要点

| 配置项 | 推荐值 |
|---|---|
| mixed-port | 7898 |
| bind-address | 127.0.0.1 |
| allow-lan | false |
| external-controller | 127.0.0.1:9098 |
| mode | rule |
| proxy group | REDDIT-POOL |
| group type | fallback 或 url-test |
| health url | https://www.google.com/generate_204 |

## 规则策略

MVP 推荐该端口全部流量走代理池：

```text
MATCH,REDDIT-POOL
```

后续可扩展 Reddit 域名专用规则：

```text
DOMAIN-SUFFIX,reddit.com,REDDIT-POOL
DOMAIN-SUFFIX,old.reddit.com,REDDIT-POOL
DOMAIN-SUFFIX,redd.it,REDDIT-POOL
DOMAIN-SUFFIX,redditmedia.com,REDDIT-POOL
MATCH,REDDIT-POOL
```

## 注意事项

- 不要使用 Reddit RSS URL 作为高频健康检查地址。
- 不要和 Clash Verge 的端口冲突。
- 配置生成失败时保留上一份可用配置。

## 验收标准

- 生成文件可被 Mihomo/Clash 成功加载。
- 本地 `7898` 端口可监听。
- 控制端口 `9098` 可访问。
- 不影响系统现有代理。
