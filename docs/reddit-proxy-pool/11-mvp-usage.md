# 11 - Reddit Proxy Pool MVP 使用说明

## 前置条件

默认假设 aggregator 已存在于：

```text
D:\Temp\wzdnzd-aggregator
```

如果路径不同，请修改：

```text
config/reddit-proxy-pool.json
```

运行时文件默认写入：

```text
D:\Temp\reddit-proxy-pool-runtime
```

## 配置文件

```text
config/reddit-proxy-pool.json   # 端口、路径、健康检查配置
config/proxy-sources.json       # 人工维护的代理订阅源
```

默认 Reddit 专用端口：

```text
127.0.0.1:7898
```

默认 Mihomo 控制端口：

```text
127.0.0.1:9098
```

## 命令

### 1. 更新代理池并生成配置

```powershell
python -m reddit_proxy_pool update
```

输出文件：

```text
D:\Temp\reddit-proxy-pool-runtime\generated\reddit-pool.yaml
D:\Temp\reddit-proxy-pool-runtime\state\proxy-inventory.json
D:\Temp\reddit-proxy-pool-runtime\logs\aggregator-report.json
```

### 2. 启动 Reddit 专用代理

```powershell
python -m reddit_proxy_pool start
```

### 3. 查看状态

```powershell
python -m reddit_proxy_pool status
```

### 4. 测试 Reddit RSS

```powershell
python -m reddit_proxy_pool test-reddit
```

### 5. 停止代理

```powershell
python -m reddit_proxy_pool stop
```

## 典型流程

```powershell
python -m reddit_proxy_pool update
python -m reddit_proxy_pool start
python -m reddit_proxy_pool test-reddit
python -m reddit_proxy_pool stop
```

## 注意事项

- 该 MVP 不读取浏览器 Cookie。
- 该 MVP 不修改系统代理。
- `7898` 只建议给 Reddit RSS Collector 使用。
- Reddit RSS Collector 仍然必须实现 60 秒全局限速和 403/429 冷却。
