# 多 Agent 搜索 / Tech Radar

当前项目包含两部分：

1. `reddit-proxy-pool`：用于给 Reddit RSS 提供独立代理池端口。
2. `tech-radar` 设计文档：用于后续开发科技新闻采集、去重、排序和榜单工具。

## Reddit Proxy Pool 快速流程

```powershell
python -m reddit_proxy_pool update
python -m reddit_proxy_pool start
python -m reddit_proxy_pool test-reddit
python -m reddit_proxy_pool stop
```

默认端口：

```text
Reddit RSS 代理入口: 127.0.0.1:7898
Mihomo 控制端口:   127.0.0.1:9098
```

默认运行时目录：

```text
D:\Temp\reddit-proxy-pool-runtime
```

## Tech Radar 快速流程

初始化数据库和 Worker 状态：

```powershell
python -m tech_radar init
```

运行一轮到期 Worker，并在采集后自动更新榜单：

```powershell
python -m tech_radar run-once --max-workers 7
```

查看状态：

```powershell
python -m tech_radar status
```

从已入库 RawItem 重建榜单并导出：

```powershell
python -m tech_radar rebuild --limit 500 --top 50 --format all
```

常驻运行：

```powershell
python -m tech_radar daemon --poll-seconds 60
```

默认运行时目录：

```text
D:\Temp\tech-radar-runtime
```

## 文档入口

```text
docs/reddit-proxy-pool/README.md
docs/reddit-proxy-pool/11-mvp-usage.md
docs/tech-radar/README.md
```
