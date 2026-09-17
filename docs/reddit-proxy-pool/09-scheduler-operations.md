# 09 - Scheduler & Operations：调度与运维模块

## 模块目标

定义代理池如何被周期性更新、启动、停止和检查。

## MVP 运维动作

| 动作 | 说明 |
|---|---|
| update-pool | 更新代理源并生成配置 |
| start-reddit-proxy | 启动 Reddit 专用 Mihomo |
| stop-reddit-proxy | 停止 Reddit 专用 Mihomo |
| check-reddit-proxy | 检查 7898 是否可用 |
| test-reddit-rss | 单次请求 Reddit RSS 验证 |

## 推荐调度

| 任务 | 频率 |
|---|---|
| 代理源更新 | 每 2-6 小时 |
| 节点健康检查 | 每 30-60 分钟 |
| Mihomo 进程检查 | 每 5-10 分钟 |
| Reddit RSS 请求 | 全局每 60 秒最多 1 次 |

## Windows 运行建议

MVP 阶段优先使用 Windows Task Scheduler。

稳定后可考虑：

- 本地常驻服务。
- Docker Compose。
- Linux cron/systemd。

## 回滚策略

- 新配置生成失败时保留上一份可用配置。
- 新配置健康节点数为 0 时不覆盖线上配置。
- Mihomo 重启失败时保持旧实例运行。

## 验收标准

- 能手动完成完整更新流程。
- 能定时更新代理池。
- 更新失败不会破坏当前可用代理。
