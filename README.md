# Tech Radar｜多源科技信息采集与榜单系统

> 用可调度 Worker 收集科技资讯，把原始条目归并为事件，再形成可追溯的热点榜单。

早期项目名为“多 Agent 搜索”。**当前核心是多 Worker 编排、信息处理流水线与可选 LLM 编辑评分，不是通用自主多智能体框架。** 仓库已有可执行代码、HTTP 服务、内置看板和验证脚本，不仅是设计文档。

## 核心能力

| 层次 | 已实现内容 |
| --- | --- |
| 来源 | 分类 RSS、Reddit 本地产物读取、可选 GitHub Releases / Trending |
| 调度 | Worker 注册、到期执行、状态记录、常驻轮询 |
| 处理 | RawItem 持久化、事件去重与聚合、规则评分、榜单快照 |
| 模型 | 可选候选事件编辑评分、缓存、与规则分融合 |
| 服务 | 标准库 HTTP 服务、内置榜单页面、状态与原始条目接口 |
| 导出 | JSON / Markdown 榜单 |
| 辅助 | 独立 Reddit RSS 代理池工具与部署文档 |

## 架构

```text
config/sources → Worker 注册 → 调度器 → RawItem / SourceRun / WorkerState
                                              ↓ SQLite
                                  去重与事件聚合 → 规则评分
                                              ↓ 可选模型评分
                                      榜单快照与导出
                                              ↓
                                    内置 Web / HTTP API
```

主链路使用 Python、Pydantic、SQLite、Feedparser 和标准库 HTTP 服务。`frontend/` 是额外 Next.js / React 前端目录，**不是运行 Python 内置看板的前置依赖**，不能将两套界面视为已经完全统一的部署产物。

## 快速开始

建议 Python 3.11+。以下在仓库根目录的 PowerShell 中执行：

```powershell
git clone https://github.com/AdS4TN/multi-agent-search.git
cd multi-agent-search
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m tech_radar --runtime-dir ./runtime init
python -m tech_radar --runtime-dir ./runtime status
python -m tech_radar --runtime-dir ./runtime run-once --max-workers 7
python -m tech_radar --runtime-dir ./runtime serve --host 127.0.0.1 --port 5080
```

打开 <http://127.0.0.1:5080>。`serve` 会启动后台采集循环；`init` 只初始化数据库与 Worker 状态，不会产生真实榜单。首次没有条目时应查看状态和来源配置；采集依赖外部来源可达。

**参数位置：** `--runtime-dir`、`--config-dir`、`--include-github` 是全局参数，必须放在子命令之前。显式设置 `./runtime`，避免使用源码中旧的 `D:/Temp` 默认目录。

### 数据源与常用操作

- `config/sources/rss-*.json`：RSS 来源及执行间隔。
- `config/sources/reddit.json`：读取 `reddit_monitor_dir` 下的监测产物，不代替上游采集器；未准备产物时可先将 `enabled` 设为 `false`。
- `config/sources/github-*.json`：默认不启用，按需添加 `--include-github`。

```powershell
python -m tech_radar --runtime-dir ./runtime --include-github run-once --max-workers 10
python -m tech_radar --runtime-dir ./runtime rebuild --limit 500 --top 50 --format all
python -m tech_radar --runtime-dir ./runtime daemon --poll-seconds 60
```

`daemon` 负责常驻调度；需要采集后自动更新榜单与提供页面时使用 `serve`，已有数据也可手动 `rebuild`。数据库与导出分别位于 `runtime/db/` 和 `runtime/exports/`。

## 可选模型评分

模型不是基础采集和规则榜单的必需依赖。通过进程环境配置自己的服务；该模块不承诺自动读取根目录 `.env`：

```powershell
$env:TECH_RADAR_LLM_BASE_URL = "https://your-model-service.example/v1"
$env:TECH_RADAR_LLM_API_KEY = "替换为本地密钥，不要提交"
$env:TECH_RADAR_LLM_MODEL = "替换为服务支持的模型"
python -m tech_radar --runtime-dir ./runtime rebuild --llm-score --llm-candidates 30 --llm-weight 0.3
```

域名是占位示例。模型调用可能产生费用，评分不等于事实核验，仍需检查来源。

## HTTP 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/api/status` | Worker 与数据库状态 |
| GET | `/api/leaderboard` | 当前榜单 |
| GET | `/api/raw` | 最近原始条目 |
| POST | `/api/run-once` | 手动采集 |

入口为 `tech_radar/service.py`。没有成熟的认证与权限体系，不应直接把采集控制接口暴露公网；示例显式绑定回环地址。

## Reddit 代理池：独立可选模块

需要自行准备聚合器、Mihomo 等组件，以及有权使用的来源，不属于看板的一键启动范围。

```powershell
python -m reddit_proxy_pool update
python -m reddit_proxy_pool start
python -m reddit_proxy_pool test-reddit
python -m reddit_proxy_pool stop
```

先阅读 [MVP 使用说明](docs/reddit-proxy-pool/11-mvp-usage.md)，检查 `config/reddit-proxy-pool.json` 的本机路径。仓库已移除个人订阅及凭据；公共示例不代表可用性保证。不要提交私人订阅 URL 或采集产物。

## 目录与阅读顺序

```text
config/sources/          Worker 配置
tech_radar/models/      数据模型
tech_radar/workers/     采集 / 导入
tech_radar/orchestrator/ 调度与执行
tech_radar/storage/     SQLite 持久化
tech_radar/ranking/     去重与榜单
tech_radar/scoring/     模型评分
tech_radar/web/         内置看板
reddit_proxy_pool/     独立代理池工具
frontend/              可选 Next.js 前端
scripts/、tests/       工具与验证
```

建议阅读 `tech_radar/cli.py` → `tech_radar/app_runtime.py` → `tech_radar/orchestrator/` → `tech_radar/ranking/`。

## 验证

本地核验（2026-09-18，Python 3.12）：图片提取 / 导出测试 4 项通过，CLI 帮助、空库初始化及状态查询通过。测试存在依赖弃用警告；未执行真实外部采集与模型评分。

```powershell
python -m compileall -q tech_radar reddit_proxy_pool
python -m tech_radar --help
python -m pip install pytest
python -m pytest tests/test_image_extraction.py -q
```

`test_m1.py`、`test_m2.py`、`test_leaderboard.py` 等包含脚本式验收和固定目录；部分需要网络或已有数据，**不能把整个 `tests/` 无条件当作隔离的 pytest 单元测试套件**。本次整理不据此宣称全链路验收通过。

## 当前边界

- 单机原型，未提供分布式队列、多租户隔离或生产 SLA。
- 来源可用性、页面结构和配额会影响采集结果。
- 额外前端仍保留模板文档及依赖，需单独配置验证；优先使用内置看板。
- 仓库为整理后的源码快照，不包含个人订阅、数据库与日志；未附独立 LICENSE 文件。

进一步阅读：[Tech Radar 文档](docs/tech-radar/README.md) · [代理池文档](docs/reddit-proxy-pool/README.md) · [产品说明](PRODUCT.md)。
