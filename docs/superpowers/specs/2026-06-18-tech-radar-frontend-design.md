# Tech Radar 前端设计规格

日期：2026-06-18

## 目标

为 Tech Radar 科技新闻采集系统提供一个可直接部署在现有 `5080` 服务上的前端界面。前端参考 Stitch MCP 最新项目 `Multi-Source Tech Feed Dashboard` 的视觉框架：暗色控制台、霓虹青主色、玻璃态模块、Sora 标题与 JetBrains Mono 数据文本。

## 信息架构

采用三页结构：

1. **总榜首页 `/`**
   - 默认进入页面。
   - 展示当前科技新闻 Top 榜、重点新闻、信源构成、采集状态概览。
   - 主要解决“今天发生了什么”的问题。

2. **信源事件详情 `/sources`**
   - 作为导航栏独立页面。
   - 按信源、主题、事件聚合查看原始新闻与榜单事件。
   - 支持选择具体信源后查看该信源最近采集的 RawItem。
   - 主要解决“每个信源贡献了什么事件”的问题。

3. **运维监控 `/ops`**
   - 作为导航栏独立二级页面。
   - 展示 Worker 状态、启用/禁用、下次调度、最近错误、运行时信息、RawItem/NewsEvent 数量。
   - 提供手动触发采集入口，调用现有 `POST /api/run-once`。
   - 主要解决“采集系统是否健康”的问题。

## 技术方案

采用 **静态前端 + 现有 Python HTTP 服务托管**：

- 新增 `tech_radar/web/index.html`
- 新增 `tech_radar/web/styles.css`
- 新增 `tech_radar/web/app.js`
- 修改 `tech_radar/service.py`：
  - `/`、`/sources`、`/ops` 返回前端入口 HTML。
  - `/web/*` 提供 CSS/JS 静态资源。
  - API 保持向后兼容。

该方案避免新增 Node/Vite 服务，部署仍然只需要 `tech-radar.service` 一个 systemd 服务和 `5080` 一个端口。

## 页面设计

### 总榜首页

- 顶部为固定导航：品牌、总榜、信源事件、运维监控、刷新按钮。
- 首屏使用控制台式 Hero：
  - 左侧显示榜单更新时间、事件总数、RawItem 总数。
  - 中间显示 Top 1 重点事件卡片。
  - 右侧显示采集健康、Worker 数量、Reddit/代理池提示。
- 下方主体：
  - 左侧 Top 榜列表。
  - 右侧主题分布、来源分布、系统状态小面板。

### 信源事件详情

- 左侧信源列表，显示每个 source_id 的数量。
- 中间显示所选信源的 RawItem 列表。
- 右侧显示当前信源摘要：数量、最近更新时间、来源类型推断、关联主题关键词。
- 支持搜索标题关键词和选择信源。

### 运维监控

- Worker 状态卡片：enabled、due_in_seconds、last_success_at、consecutive_failures、last_error。
- 服务运行时卡片：poll_seconds、max_workers、runtime_dir、config_dir。
- 数据库概览：workers_total、workers_enabled、workers_due、raw_items_count、news_events_count。
- 手动采集按钮：执行 `POST /api/run-once`，展示返回摘要。

## 数据接口

复用现有接口：

- `GET /api/status`
- `GET /api/leaderboard`
- `GET /api/raw?limit=500`
- `POST /api/run-once`

前端要对字段缺失保持容错：如果某些字段为空，显示 `—`，不能导致页面崩溃。

## 视觉规范

- 背景：深色空间感背景 `#0b0e12`。
- 主色：霓虹青 `#00ffc2`。
- 辅色：冰蓝 `#0cb3ff`。
- 危险色：柔红 `#ff6b6b`。
- 字体：标题优先 `Sora`，数据与正文优先 `JetBrains Mono`，通过 Google Fonts 加载；失败时回退系统字体。
- 组件：玻璃态面板、细描边、低强度发光、紧凑信息密度。

## 验收标准

1. 访问 `/` 能看到总榜首页，不再是旧版简单列表。
2. 导航可以切换到 `/sources` 与 `/ops`，浏览器刷新后仍能停留在对应页面。
3. 首页能展示榜单 Top 新闻、状态指标和来源分布。
4. 信源页能按 source_id 查看原始条目。
5. 运维页能展示 Worker 状态和手动触发采集结果。
6. API 错误或数据为空时页面有降级提示。
7. 不新增独立前端端口；部署后仍通过 `http://112.74.55.38:5080/` 访问。
