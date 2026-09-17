# 07 - Reddit RSS Proxy Policy：Reddit 请求策略模块

## 模块目标

定义 Reddit RSS Collector 如何使用 `127.0.0.1:7898`，以及如何处理限速、缓存、403/429 冷却。

## 职责

- 强制 Reddit RSS 请求走 `7898`。
- 管理全局 Reddit RSS 请求频率。
- 管理 subreddit 级别冷却。
- 管理 403/429 处理策略。

## 代理规则

```text
*.reddit.com RSS → http://127.0.0.1:7898
old.reddit.com RSS → http://127.0.0.1:7898
redd.it 相关请求 → http://127.0.0.1:7898
普通 RSS → direct 或默认代理，不走 7898
```

## 限速策略

Reddit RSS 推荐：

```text
全局每 60 秒最多 1 次请求
单 subreddit 独立记录 last_fetch_at
请求失败后按错误类型冷却
```

## 错误处理

| 返回/错误 | 处理 |
|---|---|
| 200 | 解析 RSS，更新缓存 |
| 304 | 使用缓存 |
| 429 | 冷却 10-30 分钟，不立即重试 |
| 403 | 冷却 30-60 分钟，不连续换代理打 |
| timeout | 可最多换代理重试 1 次 |
| XML 解析失败 | 保留原响应摘要，标记 parse_error |

## 缓存策略

- 保存最近一次成功 RSS 内容。
- 支持 ETag / Last-Modified 时优先使用条件请求。
- 失败时优先使用缓存，不强行重试。

## 验收标准

- Reddit RSS 请求实际走 `7898`。
- 403/429 后停止请求并进入冷却。
- 普通 RSS 不受 Reddit 代理池影响。
