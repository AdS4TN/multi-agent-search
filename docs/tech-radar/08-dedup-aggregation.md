# 08. 主节点去重与事件聚合

## 1. 模块目标

去重与事件聚合模块由主节点执行，负责把多个 Worker 返回的 RawItem 合并成更少、更清晰的 NewsEvent。该模块是榜单质量的核心。

## 2. 为什么去重放在主节点

子节点只能看到局部信源，而热点新闻经常跨多个来源出现：

```text
官方博客
科技媒体报道
Reddit 讨论
GitHub release
```

只有主节点拥有全局视野，才能判断这些 RawItem 是否属于同一事件。

## 3. 去重层级

第一版采用三层规则：

| 层级 | 方法 | 说明 |
|---|---|---|
| L1 | canonical_url 完全匹配 | 最可靠 |
| L2 | 标题规范化后高度相似 | 处理转载和同题报道 |
| L3 | 主题关键词 + 时间窗口接近 | 处理标题略有差异的同事件 |

第一版不做 embedding 语义去重。

## 4. URL 规范化

URL 规范化目标：同一文章的跟踪参数或轻微差异不导致重复。

需要处理：

| 项 | 处理 |
|---|---|
| http/https | 优先保留实际 canonical，必要时统一 |
| trailing slash | 规范化 |
| UTM 参数 | 移除 |
| 常见 tracking 参数 | 移除 |
| fragment | 通常移除 |
| Reddit URL | 保留 comments post id |
| GitHub release URL | 规范到 owner/repo/releases/tag/tag |

## 5. 标题规范化

标题规范化用于相似度比较：

| 处理 | 说明 |
|---|---|
| 大小写统一 | 英文标题转小写比较 |
| 去除多余空白 | 合并连续空格 |
| 去除站点后缀 | 如 “- The Verge” |
| 去除常见标点差异 | 降低误差 |
| 保留关键实体 | 公司、模型名、项目名不能删除 |

## 6. 事件聚合策略

聚合流程：

```text
新 RawItem
  ↓
查找 URL 完全匹配事件
  ↓ 无
查找标题相似候选
  ↓ 无
查找时间窗口内主题候选
  ↓ 无
创建新 NewsEvent
```

当 RawItem 合并到已有事件时：

| 字段 | 合并策略 |
|---|---|
| sources | 追加来源引用 |
| topics | 取并集 |
| latest_seen_at | 更新 |
| canonical_title | 优先官方源，其次高权重媒体，其次最清晰标题 |
| canonical_url | 优先官方源或原始发布源 |
| metadata | 保留各来源独立 metadata |

## 7. 防误合并策略

| 风险 | 防护 |
|---|---|
| 同一公司多条新闻被合并 | 时间窗口 + 关键动词差异判断 |
| 同一项目不同 release 被合并 | GitHub tag 必须区分 |
| Reddit 讨论泛化标题误合并 | Reddit 单独作为弱匹配来源 |
| 媒体 roundup 文章误合并 | roundup 类标题降低匹配置信度 |

## 8. 测试验收

| 测试项 | 验收标准 |
|---|---|
| URL 去重 | 带 UTM 和不带 UTM 的同链接合并 |
| 标题去重 | 同一新闻不同媒体标题相似时合并 |
| GitHub 区分 | 同一 repo 不同 tag release 不合并 |
| 误合并控制 | 同一公司一天内两条不同新闻不合并 |
| Reddit 合并 | Reddit 热帖能与对应官方/媒体新闻合并 |
| 事件可追溯 | NewsEvent 能列出所有 RawItem 来源 |
| 重建能力 | 从 raw_items 重新构建事件结果稳定 |
