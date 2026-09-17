"use client";

import { useEffect, useMemo, useState } from "react";
import { BlogCard } from "@/components/blog-card";
import { TagFilter } from "@/components/tag-filter";
import { FlickeringGrid } from "@/components/magicui/flickering-grid";

type View = "home" | "sources" | "ops";

type LeaderboardItem = {
  rank?: number;
  title?: string;
  reason?: string;
  url?: string;
  image_url?: string;
  image?: string | Record<string, unknown>;
  thumbnail?: string;
  thumbnail_url?: string;
  image_source?: string;
  image_alt?: string;
  updated_at?: string;
  score?: number;
  source_names?: string[];
  topics?: string[];
};

type RawItem = {
  title?: string;
  url?: string;
  raw_text?: string;
  source_id?: string;
  source_name?: string;
  source_type?: string;
  worker_id?: string;
  published_at?: string;
  image_url?: string;
  image?: string | Record<string, unknown>;
  thumbnail?: string;
  thumbnail_url?: string;
  image_source?: string;
  image_alt?: string;
  topics?: string[];
  metadata?: Record<string, unknown>;
};

type WorkerState = {
  worker_id?: string;
  enabled?: boolean;
  due_in_seconds?: number;
  consecutive_failures?: number;
  last_success_at?: string;
  last_error?: string;
};

type StatusPayload = {
  news_events_count?: number;
  raw_items_count?: number;
  workers_total?: number;
  workers_enabled?: number;
  workers_due?: number;
  workers?: WorkerState[];
  service?: Record<string, unknown>;
};

type LeaderboardPayload = {
  items?: LeaderboardItem[];
};

type RawPayload = {
  items?: RawItem[];
};

type SourceSummary = {
  id: string;
  name: string;
  type: string;
  count: number;
  latest: string;
};

const viewCopy: Record<View, { title: string; description: string }> = {
  home: {
    title: "Tech Radar",
    description: "",
  },
  sources: {
    title: "Source Events",
    description: "",
  },
  ops: {
    title: "Operations",
    description: "",
  },
};

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `${response.status} ${response.statusText}${text ? ` · ${text.slice(0, 160)}` : ""}`,
    );
  }

  return response.json();
}

export function TechRadarPage({ view }: { view: View }) {
  const [status, setStatus] = useState<StatusPayload>({});
  const [leaderboard, setLeaderboard] = useState<LeaderboardPayload>({});
  const [raw, setRaw] = useState<RawPayload>({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [selectedTag, setSelectedTag] = useState("All");
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);

  const load = async () => {
    setError("");
    setLoading(true);
    try {
      const [nextStatus, nextLeaderboard, nextRaw] = await Promise.all([
        fetchJson<StatusPayload>("/api/status"),
        fetchJson<LeaderboardPayload>("/api/leaderboard"),
        fetchJson<RawPayload>("/api/raw?limit=500"),
      ]);
      setStatus(nextStatus || {});
      setLeaderboard(nextLeaderboard || {});
      setRaw(nextRaw || {});
      setLoadedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const runOnce = async () => {
    if (running) return;
    setRunning(true);
    setError("");
    try {
      await fetchJson("/api/run-once", { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  };

  const items = useMemo(() => leaderboard.items || [], [leaderboard.items]);
  const rawItems = useMemo(() => raw.items || [], [raw.items]);
  const homeTags = useMemo(() => buildTopicTags(items, rawItems), [items, rawItems]);
  const sourceSummaries = useMemo(() => buildSourceSummaries(rawItems), [rawItems]);
  const sourceTags = useMemo(
    () => ["All", ...sourceSummaries.slice(0, 24).map((source) => source.name)],
    [sourceSummaries],
  );

  const activeTags = view === "sources" ? sourceTags : homeTags.map((tag) => tag.key);
  const activeTag = activeTags.includes(selectedTag) ? selectedTag : "All";

  const filteredLeaderboard = useMemo(() => {
    if (activeTag === "All") return items;
    return items.filter((item) => (item.topics || []).includes(activeTag));
  }, [activeTag, items]);

  const filteredRaw = useMemo(() => {
    if (activeTag === "All") return rawItems;
    return rawItems.filter(
      (item) => (item.source_name || item.source_id || "unknown") === activeTag,
    );
  }, [activeTag, rawItems]);

  const tagCounts = useMemo(() => {
    if (view === "sources") {
      return Object.fromEntries([
        ["All", rawItems.length],
        ...sourceSummaries.map((source) => [source.name, source.count]),
      ]);
    }
    return Object.fromEntries(homeTags.map((tag) => [tag.key, tag.count]));
  }, [homeTags, rawItems.length, sourceSummaries, view]);

  return (
    <main className="min-h-screen bg-background relative">
      <div className="absolute top-0 left-0 z-0 w-full h-[200px] [mask-image:linear-gradient(to_top,transparent_25%,black_95%)]">
        <FlickeringGrid
          className="absolute top-0 left-0 size-full"
          squareSize={4}
          gridGap={6}
          color="#6B7280"
          maxOpacity={0.2}
          flickerChance={0.05}
        />
      </div>

      <section className="p-6 border-b border-border flex flex-col gap-6 min-h-[250px] justify-center relative z-10">
        <div className="max-w-7xl mx-auto w-full flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <h1 className="font-medium text-4xl md:text-5xl tracking-tighter">
              {viewCopy[view].title}
            </h1>
            {viewCopy[view].description ? (
              <p className="text-muted-foreground text-sm md:text-base lg:text-lg max-w-3xl">
                {viewCopy[view].description}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs font-medium text-muted-foreground">
            <span>{loadedAt ? formatDate(loadedAt.toISOString()) : "未同步"}</span>
            <span>{status.news_events_count ?? items.length} events</span>
            <span>{status.raw_items_count ?? rawItems.length} raw items</span>
            {error ? <span className="text-destructive">{error}</span> : null}
          </div>
        </div>

        {view !== "ops" ? (
          <div className="max-w-7xl mx-auto w-full">
            <TagFilter
              tags={activeTags}
              selectedTag={activeTag}
              tagCounts={tagCounts}
              onSelect={setSelectedTag}
            />
          </div>
        ) : null}

        <div className="max-w-7xl mx-auto w-full flex flex-wrap gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading || running}
            className="h-8 px-3 rounded-lg border border-border text-sm font-medium hover:bg-muted transition-colors disabled:opacity-50"
          >
            {loading ? "同步中" : "刷新数据"}
          </button>
          {view === "ops" ? (
            <button
              type="button"
              onClick={runOnce}
              disabled={loading || running}
              className="h-8 px-3 rounded-lg border border-primary bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {running ? "采集中" : "运行一轮"}
            </button>
          ) : null}
        </div>
      </section>

      {renderBody({
        view,
        loading,
        error,
        items: filteredLeaderboard,
        rawItems: filteredRaw,
        sourceSummaries,
        status,
      })}
    </main>
  );
}

function renderBody({
  view,
  loading,
  error,
  items,
  rawItems,
  sourceSummaries,
  status,
}: {
  view: View;
  loading: boolean;
  error: string;
  items: LeaderboardItem[];
  rawItems: RawItem[];
  sourceSummaries: SourceSummary[];
  status: StatusPayload;
}) {
  if (loading) {
    return <EmptyBlock title="正在连接情报流" text="" />;
  }

  if (error) {
    return <EmptyBlock title="数据接口暂不可用" text={error} />;
  }

  if (view === "sources") {
    return <SourceGrid rawItems={rawItems} sourceSummaries={sourceSummaries} />;
  }

  if (view === "ops") {
    return <OpsGrid status={status} />;
  }

  return <LeaderboardGrid items={items} />;
}

function LeaderboardGrid({ items }: { items: LeaderboardItem[] }) {
  return (
    <div className="max-w-7xl mx-auto w-full px-6 lg:px-0">
      <div
        className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 relative overflow-hidden border-x border-border ${
          items.length < 4 ? "border-b" : "border-b-0"
        }`}
      >
        {items.length ? (
          items.map((item) => (
            <BlogCard
              key={`${item.rank}-${item.url}-${item.title}`}
              url={safeHref(item.url)}
              title={item.title || "未命名事件"}
              description={
                item.reason ||
                `${(item.source_names || []).slice(0, 3).join(" · ") || "来源未记录"} · score ${formatScore(item.score)}`
              }
              date={`#${item.rank ?? "—"} · ${formatDate(item.updated_at)} · score ${formatScore(item.score)}`}
              thumbnail={imageUrlFromRecord(item)}
              thumbnailAlt={item.image_alt || item.title || "新闻配图"}
            />
          ))
        ) : (
          <EmptyBlock title="暂无榜单事件" text="等待采集 Worker 写入榜单快照。" compact />
        )}
      </div>
    </div>
  );
}

function SourceGrid({
  rawItems,
  sourceSummaries,
}: {
  rawItems: RawItem[];
  sourceSummaries: SourceSummary[];
}) {
  const summaryByName = new Map(sourceSummaries.map((source) => [source.name, source]));

  return (
    <div className="max-w-7xl mx-auto w-full px-6 lg:px-0">
      <div
        className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 relative overflow-hidden border-x border-border ${
          rawItems.length < 4 ? "border-b" : "border-b-0"
        }`}
      >
        {rawItems.length ? (
          rawItems.slice(0, 180).map((item, index) => {
            const sourceName = item.source_name || item.source_id || "unknown";
            const source = summaryByName.get(sourceName);
            return (
              <BlogCard
                key={`${item.url}-${item.published_at}-${index}`}
                url={safeHref(item.url)}
                title={item.title || "未命名条目"}
                description={stripHtml(item.raw_text) || `${sourceName} · ${item.worker_id || "worker"}`}
                date={`${sourceName} · ${formatDate(item.published_at)}${source ? ` · ${source.count} items` : ""}`}
                thumbnail={imageUrlFromRecord(item)}
                thumbnailAlt={item.image_alt || item.title || "新闻配图"}
              />
            );
          })
        ) : (
          <EmptyBlock title="暂无原始事件" text="当前筛选条件下没有 RawItem。" compact />
        )}
      </div>
    </div>
  );
}

function OpsGrid({ status }: { status: StatusPayload }) {
  const workers = status.workers || [];
  const service = status.service || {};
  const cards = [
    {
      title: "Worker 状态",
      description: `${status.workers_enabled ?? "—"}/${status.workers_total ?? "—"} enabled · ${status.workers_due ?? 0} due`,
      date: "orchestrator",
    },
    {
      title: "采集结果",
      description: `${status.news_events_count ?? "—"} events · ${status.raw_items_count ?? "—"} raw items`,
      date: "storage",
    },
    {
      title: "LLM Scoring",
      description: `enabled ${String(service.llm_enabled ?? false)} · scores ${String(service.llm_scores_count ?? "—")}`,
      date: "ranking",
    },
    {
      title: "调度配置",
      description: `poll ${String(service.poll_seconds ?? "—")}s · max workers ${String(service.max_workers ?? "—")}`,
      date: "runtime",
    },
    ...workers.slice(0, 24).map((worker) => ({
      title: worker.worker_id || "unknown-worker",
      description: `${worker.enabled ? "enabled" : "disabled"} · ${worker.consecutive_failures || 0} failures · ${formatDue(worker.due_in_seconds)}`,
      date: worker.last_error || `last success ${formatDate(worker.last_success_at)}`,
    })),
  ];

  return (
    <div className="max-w-7xl mx-auto w-full px-6 lg:px-0">
      <div
        className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 relative overflow-hidden border-x border-border ${
          cards.length < 4 ? "border-b" : "border-b-0"
        }`}
      >
        {cards.map((card) => (
          <InfoCard key={`${card.title}-${card.date}`} {...card} />
        ))}
      </div>
    </div>
  );
}

function InfoCard({
  title,
  description,
  date,
}: {
  title: string;
  description: string;
  date: string;
}) {
  return (
    <article className="group block relative before:absolute before:-left-0.5 before:top-0 before:z-10 before:h-screen before:w-px before:bg-border before:content-[''] after:absolute after:-top-0.5 after:left-0 after:z-0 after:h-px after:w-screen after:bg-border after:content-[''] md:border-r border-border border-b-0">
      <div className="p-6 flex min-h-48 flex-col gap-2">
        <h3 className="text-xl font-semibold text-card-foreground tracking-tight">{title}</h3>
        <p className="text-muted-foreground text-sm break-words">{description}</p>
        <time className="mt-auto block text-sm font-medium text-muted-foreground break-words">
          {date}
        </time>
      </div>
    </article>
  );
}

function EmptyBlock({
  title,
  text,
  compact = false,
}: {
  title: string;
  text: string;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "col-span-full p-6" : "max-w-7xl mx-auto w-full p-6"}>
      <div className="border border-border rounded-lg bg-card p-6">
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {text ? <p className="mt-2 text-sm text-muted-foreground">{text}</p> : null}
      </div>
    </div>
  );
}

function buildTopicTags(items: LeaderboardItem[], rawItems: RawItem[]) {
  const source = items.length ? items : rawItems;
  const counts = new Map<string, number>();
  for (const item of source) {
    for (const topic of item.topics || []) {
      counts.set(topic, (counts.get(topic) || 0) + 1);
    }
  }
  return [
    { key: "All", count: source.length },
    ...Array.from(counts, ([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
      .slice(0, 12),
  ];
}

function buildSourceSummaries(items: RawItem[]): SourceSummary[] {
  const map = new Map<string, SourceSummary>();
  for (const item of items) {
    const id = item.source_id || item.source_name || "unknown";
    const name = item.source_name || id;
    if (!map.has(name)) {
      map.set(name, {
        id,
        name,
        type: item.source_type || "unknown",
        count: 0,
        latest: "",
      });
    }
    const summary = map.get(name)!;
    summary.count += 1;
    if (!summary.latest || new Date(item.published_at || 0) > new Date(summary.latest || 0)) {
      summary.latest = item.published_at || summary.latest;
    }
  }
  return Array.from(map.values()).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

function safeHref(url?: string) {
  return /^https?:\/\//i.test(url || "") ? url! : "#";
}

function safeImage(url?: string) {
  return /^https?:\/\//i.test(url || "") ? url : undefined;
}

function imageUrlFromRecord(item: Record<string, unknown>) {
  return safeImage(firstString(
    item.image_url,
    item.thumbnail,
    item.thumbnail_url,
    nestedString(item.image, "url"),
    nestedString(item.image, "image_url"),
    nestedString(item.metadata, "image_url"),
    nestedString(item.metadata, "thumbnail"),
    nestedString(item.metadata, "thumbnail_url"),
    nestedString(item.metadata, "preview_image"),
    nestedString(item.metadata, "og_image"),
    nestedString(nestedRecord(item.metadata, "image"), "url"),
    nestedString(nestedRecord(item.metadata, "image"), "image_url"),
  ));
}

function nestedRecord(value: unknown, key: string): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const nested = (value as Record<string, unknown>)[key];
  if (!nested || typeof nested !== "object" || Array.isArray(nested)) return undefined;
  return nested as Record<string, unknown>;
}

function nestedString(value: unknown, key: string) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const nested = (value as Record<string, unknown>)[key];
  return typeof nested === "string" ? nested : undefined;
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function stripHtml(value?: string) {
  return String(value || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 220);
}

function formatScore(value?: number) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number >= 100 ? number.toFixed(0) : number.toFixed(1);
}

function formatDate(value?: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDue(seconds?: number) {
  const value = Number(seconds || 0);
  if (value <= 0) return "due now";
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}
