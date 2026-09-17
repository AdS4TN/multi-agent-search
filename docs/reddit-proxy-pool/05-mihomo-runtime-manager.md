# 05 - Mihomo Runtime Manager：运行时管理模块

## 模块目标

管理 Reddit 专用 Mihomo 实例的启动、停止、重启和状态检查。

## 职责

- 检查 `7898` 和 `9098` 端口是否被占用。
- 启动独立 Mihomo/Clash 进程。
- 停止 Reddit 专用实例。
- 检查实例是否健康。
- 记录运行日志。

## 输入

```text
Mihomo 可执行文件路径
reddit-pool.yaml 配置路径
端口配置
```

## 输出

```text
进程状态
端口状态
runtime/logs/mihomo-runtime.log
```

## 生命周期

```text
prepare → port_check → start → wait_ready → health_probe → running
running → reload_config / restart / stop
```

## 端口规划

| 用途 | 端口 |
|---|---|
| Reddit 代理入口 | 7898 |
| Reddit 控制端口 | 9098 |
| 当前 Clash Verge | 7897，不能占用 |

## 错误处理

| 场景 | 处理 |
|---|---|
| 7898 被占用 | 拒绝启动并提示占用进程 |
| 配置无效 | 不启动，保留错误日志 |
| 启动后端口未打开 | 终止进程并标记启动失败 |
| 进程异常退出 | 记录退出码，等待调度模块重启 |

## 验收标准

- 可以独立启动 Reddit Mihomo 实例。
- 可以独立停止，不影响 Clash Verge。
- 启动后 `127.0.0.1:7898` 可被 RSS Collector 使用。
