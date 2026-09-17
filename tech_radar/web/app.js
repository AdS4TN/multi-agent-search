const app = document.querySelector("#app");
const syncStatus = document.querySelector("#syncStatus");
const refreshButton = document.querySelector("#refreshButton");
const sidebarTopics = document.querySelector("#sidebarTopics");
const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
const FETCH_TIMEOUT_MS = 18000;
const EMPTY_ITEMS = Object.freeze([]);
const LOGO_LOOP_TOP_ITEMS = Object.freeze([
  { title: "Reddit", src: "/web/assets/logos/svg-display/reddit-logo-2023.svg", href: "https://www.reddit.com", height: 28 },
  { title: "Hacker News", src: "/web/assets/logos/svg-display/hacker-news-logo.svg", href: "https://news.ycombinator.com", height: 23 },
  { title: "Hugging Face", src: "/web/assets/logos/svg-display/huggingface-logo-with-title.svg", href: "https://huggingface.co/blog", height: 30 },
  { title: "OpenAI", src: "/web/assets/logos/svg-display/openai-logo.svg", href: "https://openai.com/news", height: 27 },
  { title: "GitHub", src: "/web/assets/logos/svg-display/github-logo.svg?v=white-20260621", href: "https://github.com", height: 27 },
  { title: "NVIDIA", src: "/web/assets/logos/svg-display/nvidia-logo.svg", href: "https://blogs.nvidia.com", height: 26 },
  { title: "a16z Crypto", src: "/web/assets/logos/svg-display/a16z-crypto.svg", href: "https://a16zcrypto.com", height: 28 },
  { title: "YouTube", src: "/web/assets/logos/svg-display/youtube-logo.svg?v=white-20260621", href: "https://www.youtube.com", height: 26 },
  { title: "X", src: "/web/assets/logos/svg-display/x-logo-2023.svg", href: "https://x.com", height: 29 },
]);
const LOGO_LOOP_BOTTOM_ITEMS = Object.freeze([
  { title: "Google DeepMind", src: "/web/assets/logos/svg-display/google-deepmind-logo.svg", href: "https://deepmind.google", height: 26 },
  { title: "Google AI", src: "/web/assets/logos/svg-display/google-ai-new.svg?v=display-20260621-2", href: "https://ai.google", height: 31 },
  { title: "TechCrunch", src: "/web/assets/logos/svg-display/techcrunch.svg", href: "https://techcrunch.com", height: 21 },
  { title: "MIT Technology Review", src: "/web/assets/logos/svg-display/mit-technology-review.svg", href: "https://www.technologyreview.com", height: 30 },
  { title: "IEEE Spectrum", src: "/web/assets/logos/svg-display/ieee-spectrum.svg", href: "https://spectrum.ieee.org", height: 24 },
  { title: "Product Hunt", src: "/web/assets/logos/svg-display/product-hunt-logo.svg", href: "https://www.producthunt.com", height: 26 },
  { title: "36Kr", src: "/web/assets/logos/counter-clear/36Kr-logo-crop.counterclear.png", href: "https://36kr.com", height: 29 },
  { title: "量子位", src: "/web/assets/logos/counter-clear/qbitai-logo-1.counterclear.png", href: "https://www.qbitai.com", height: 25 },
  { title: "机器之心", src: "/web/assets/logos/counter-clear/jiqizhixin.counterclear.png", href: "https://www.jiqizhixin.com", height: 27 },
  { title: "Ethereum", src: "/web/assets/logos/svg-display/ethereum-logo.svg", href: "https://ethereum.org", height: 32 },
]);
const LOGO_LOOP_ANIMATION_CONFIG = Object.freeze({ SMOOTH_TAU: 0.25, MIN_COPIES: 2, MAX_COPIES: 8, COPY_HEADROOM: 2 });
const LOGO_LOOP_DISPLAY_SCALE = 1.35;

const state = {
  status: null,
  leaderboard: null,
  raw: null,
  route: routeFromPath(location.pathname),
  selectedSourceId: "",
  loading: true,
  error: "",
  lastLoadedAt: null,
  running: false,
};

const derivedCache = {
  rawRef: null,
  rawItems: null,
  leaderboardRef: null,
  leaderboardItems: null,
  sourceRawRef: null,
  sourceStats: null,
};

let lastAnimationKey = "";
let logoLoopCleanups = [];
const logoLoopRuntime = new Map();

const routes = {
  home: "/",
  sources: "/sources",
  ops: "/ops",
};

function routeFromPath(pathname) {
  if (pathname.startsWith("/sources")) return "sources";
  if (pathname.startsWith("/ops")) return "ops";
  return "home";
}

function setSync(text, mode = "") {
  if (!syncStatus) return;
  syncStatus.textContent = text;
  syncStatus.classList.toggle("is-busy", mode === "busy");
  syncStatus.classList.toggle("is-error", mode === "error");
}

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      cache: "no-store",
      ...options,
      signal: controller.signal,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(`${response.status} ${response.statusText}${text ? ` · ${text.slice(0, 180)}` : ""}`);
    }
    return response.json();
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`请求超时：${url}`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function refreshData({ keepLoading = false } = {}) {
  if (!keepLoading) {
    state.loading = true;
    state.error = "";
    render();
  }
  setSync("SYNC · LOADING", "busy");

  try {
    const [status, leaderboard, raw] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/leaderboard"),
      fetchJson("/api/raw?limit=500"),
    ]);
    state.status = status || {};
    state.leaderboard = leaderboard || {};
    state.raw = raw || {};
    state.loading = false;
    state.error = "";
    state.lastLoadedAt = new Date();
    resetDerivedCache();
    ensureSelectedSource();
    setSync("SYNC · LIVE");
  } catch (error) {
    state.loading = false;
    state.error = error.message || String(error);
    setSync("SYNC · ERROR", "error");
  }

  render();
}

async function runOnce() {
  if (state.running) return;
  state.running = true;
  setSync("RUN · COLLECTING", "busy");
  render();
  try {
    await fetchJson("/api/run-once", { method: "POST" });
    await refreshData({ keepLoading: true });
  } catch (error) {
    state.error = error.message || String(error);
    setSync("RUN · ERROR", "error");
    render();
  } finally {
    state.running = false;
    render();
  }
}

function navigate(route) {
  if (route === state.route) return;
  state.route = route;
  const nextPath = routes[route] || "/";
  if (location.pathname !== nextPath) {
    history.pushState({ route }, "", nextPath);
  }
  ensureSelectedSource();
  render();
  app?.focus?.({ preventScroll: true });
}

function render() {
  updateNav();
  updateSidebarTopics();

  if (!app) return;
  cleanupLogoLoops();
  app.setAttribute("aria-busy", state.loading ? "true" : "false");
  app.dataset.route = state.route;
  if (state.loading) {
    app.innerHTML = loadingTemplate();
    runEntranceAnimation();
    return;
  }
  if (state.error) {
    app.innerHTML = errorTemplate(state.error);
    bindPageEvents();
    runEntranceAnimation({ force: true });
    return;
  }

  if (state.route === "sources") {
    app.innerHTML = renderSourcesPage();
  } else if (state.route === "ops") {
    app.innerHTML = renderOpsPage();
  } else {
    app.innerHTML = renderHomePage();
  }
  bindPageEvents();
  setupLogoLoops();
  runEntranceAnimation();
}

function updateNav() {
  document.querySelectorAll("[data-route]").forEach((node) => {
    node.classList.toggle("active", node.dataset.route === state.route);
    if (node.dataset.route === state.route) {
      node.setAttribute("aria-current", "page");
    } else {
      node.removeAttribute("aria-current");
    }
  });
  if (refreshButton) {
    refreshButton.disabled = state.loading || state.running;
  }
}

function updateSidebarTopics() {
  if (!sidebarTopics) return;
  const items = rawItemsList();
  const topics = topicStats(items).slice(0, 7);
  if (!topics.length) {
    sidebarTopics.innerHTML = `<span>等待数据同步…</span>`;
    return;
  }
  sidebarTopics.innerHTML = topics.map((topic) => `
    <span>
      <em>${escapeHtml(topic.key)}</em>
      <strong>${escapeHtml(topic.count)}</strong>
    </span>
  `).join("");
}

function bindPageEvents() {
}

function resetDerivedCache() {
  derivedCache.rawRef = null;
  derivedCache.rawItems = null;
  derivedCache.leaderboardRef = null;
  derivedCache.leaderboardItems = null;
  derivedCache.sourceRawRef = null;
  derivedCache.sourceStats = null;
}

function runEntranceAnimation({ force = false } = {}) {
  if (!app || !app.animate || prefersReducedMotion?.matches) return;
  const key = `${state.route}:${state.loading ? "loading" : "ready"}:${state.error ? "error" : ""}:${state.lastLoadedAt?.getTime?.() || 0}`;
  if (!force && key === lastAnimationKey) return;
  lastAnimationKey = key;

  const targets = app.querySelectorAll([
    ".workbench-toolbar",
    ".workbench-hero-copy",
    ".top-story-panel",
    ".snapshot-panel",
    ".story-tile",
    ".insights-panel",
    ".page-header",
    ".source-list-panel",
    ".source-stream-panel",
    ".source-detail-panel",
    ".ops-panel",
    ".worker-card",
    ".loading-card",
    ".error-card",
  ].join(","));

  targets.forEach((node, index) => {
    node.animate(
      [
        { opacity: 0, transform: "translate3d(0, 14px, 0) scale(0.992)" },
        { opacity: 1, transform: "translate3d(0, 0, 0) scale(1)" },
      ],
      {
        duration: 420,
        delay: Math.min(index * 34, 260),
        easing: "cubic-bezier(.22,1,.36,1)",
        fill: "both",
      },
    );
  });
}

function cleanupLogoLoops() {
  for (const cleanup of logoLoopCleanups) {
    cleanup?.();
  }
  logoLoopCleanups = [];
}

function setupLogoLoops() {
  const loops = app?.querySelectorAll?.("[data-logo-loop]") || [];
  logoLoopCleanups = Array.from(loops).map(initLogoLoop).filter(Boolean);
}

function initLogoLoop(container) {
  const track = container.querySelector(".logoloop__track");
  const seq = track?.querySelector(".logoloop__list");
  if (!track || !seq) return null;

  const loopId = container.dataset.loopId || container.getAttribute("aria-label") || Math.random().toString(36);
  const savedRuntime = logoLoopRuntime.get(loopId);
  const direction = container.dataset.direction || "left";
  const isVertical = direction === "up" || direction === "down";
  const speed = Number(container.dataset.speed || 120);
  const hoverSpeedValue = container.dataset.hoverSpeed;
  const hoverSpeed = hoverSpeedValue == null ? 0 : Number(hoverSpeedValue);
  const smoothTauValue = Number(container.dataset.smoothTau);
  const smoothTau = Number.isFinite(smoothTauValue) && smoothTauValue > 0
    ? smoothTauValue
    : LOGO_LOOP_ANIMATION_CONFIG.SMOOTH_TAU;
  const targetVelocity = logoLoopTargetVelocity(speed, direction, isVertical);

  let seqWidth = 0;
  let seqHeight = 0;
  let copyCount = LOGO_LOOP_ANIMATION_CONFIG.MIN_COPIES;
  let isHovered = false;
  let rafId = null;
  let lastTimestamp = null;
  let offset = 0;
  let velocity = 0;
  let hasInitializedOffset = false;
  let canStartAnimation = false;

  const applyTrackTransform = (nextOffset) => {
    track.style.transform = isVertical
      ? `translate3d(0, ${-nextOffset}px, 0)`
      : `translate3d(${-nextOffset}px, 0, 0)`;
  };

  const initializeOffset = (seqSize) => {
    if (!canStartAnimation || hasInitializedOffset || seqSize <= 0) return;
    const savedOffset = Number(savedRuntime?.offset);
    const savedVelocity = Number(savedRuntime?.velocity);
    const savedSeqSize = Number(savedRuntime?.seqSize);
    const savedAt = Number(savedRuntime?.timestamp);

    if (Number.isFinite(savedOffset)) {
      const baseOffset = Number.isFinite(savedSeqSize) && savedSeqSize > 0
        ? (savedOffset / savedSeqSize) * seqSize
        : savedOffset;
      const elapsed = Number.isFinite(savedAt)
        ? Math.max(0, (performance.now() - savedAt) / 1000)
        : 0;
      const projectedOffset = baseOffset + targetVelocity * elapsed;
      offset = ((projectedOffset % seqSize) + seqSize) % seqSize;
    } else {
      // 右向/下向滚动需要从上一组重复序列的位置开始，否则第一帧会从 0 跳到 -seqSize。
      offset = targetVelocity < 0 ? Math.max(0, seqSize - 0.01) : 0;
    }
    velocity = Number.isFinite(savedVelocity) ? savedVelocity : targetVelocity;
    hasInitializedOffset = true;
    applyTrackTransform(offset);
  };

  const startAnimation = () => {
    if (!canStartAnimation || rafId !== null) return;
    const seqSize = isVertical ? seqHeight : seqWidth;
    if (seqSize <= 0) return;
    initializeOffset(seqSize);
    rafId = window.requestAnimationFrame(animate);
  };

  const syncCopies = (nextCopyCount) => {
    if (nextCopyCount === copyCount && track.children.length === nextCopyCount) return;
    copyCount = nextCopyCount;
    while (track.children.length < copyCount) {
      const clone = seq.cloneNode(true);
      clone.setAttribute("aria-hidden", "true");
      track.appendChild(clone);
    }
    while (track.children.length > copyCount) {
      track.lastElementChild?.remove();
    }
    Array.from(track.children).forEach((list, index) => {
      if (index > 0) {
        list.setAttribute("aria-hidden", "true");
      } else {
        list.removeAttribute("aria-hidden");
      }
    });
  };

  const updateDimensions = () => {
    const containerWidth = container.clientWidth || 0;
    const sequenceRect = seq.getBoundingClientRect?.();
    const sequenceWidth = sequenceRect?.width || 0;
    const sequenceHeight = sequenceRect?.height || 0;

    if (isVertical) {
      const parentHeight = container.parentElement?.clientHeight || 0;
      if (parentHeight > 0) {
        const targetHeight = Math.ceil(parentHeight);
        if (container.style.height !== `${targetHeight}px`) {
          container.style.height = `${targetHeight}px`;
        }
      }
      if (sequenceHeight > 0) {
        seqHeight = Math.ceil(sequenceHeight);
        const viewport = container.clientHeight || parentHeight || sequenceHeight;
        const copiesNeeded = Math.ceil(viewport / sequenceHeight) + LOGO_LOOP_ANIMATION_CONFIG.COPY_HEADROOM;
        syncCopies(clampLogoLoopCopies(copiesNeeded));
        initializeOffset(seqHeight);
        startAnimation();
      }
      return;
    }

    if (sequenceWidth > 0) {
      seqWidth = Math.ceil(sequenceWidth);
      const copiesNeeded = Math.ceil(containerWidth / sequenceWidth) + LOGO_LOOP_ANIMATION_CONFIG.COPY_HEADROOM;
      syncCopies(clampLogoLoopCopies(copiesNeeded));
      initializeOffset(seqWidth);
      startAnimation();
    }
  };

  const animate = (timestamp) => {
    const seqSize = isVertical ? seqHeight : seqWidth;
    if (lastTimestamp === null) {
      lastTimestamp = timestamp;
    }

    const deltaTime = Math.max(0, timestamp - lastTimestamp) / 1000;
    lastTimestamp = timestamp;

    const target = isHovered && Number.isFinite(hoverSpeed) ? hoverSpeed : targetVelocity;
    const easingFactor = 1 - Math.exp(-deltaTime / smoothTau);
    velocity += (target - velocity) * easingFactor;

    if (seqSize > 0) {
      offset = ((offset + velocity * deltaTime) % seqSize + seqSize) % seqSize;
      applyTrackTransform(offset);
    }

    rafId = window.requestAnimationFrame(animate);
  };

  const handleMouseEnter = () => {
    if (Number.isFinite(hoverSpeed)) isHovered = true;
  };
  const handleMouseLeave = () => {
    if (Number.isFinite(hoverSpeed)) isHovered = false;
  };

  track.addEventListener("mouseenter", handleMouseEnter);
  track.addEventListener("mouseleave", handleMouseLeave);

  const observerCleanups = [];
  if (window.ResizeObserver) {
    const containerObserver = new ResizeObserver(updateDimensions);
    const seqObserver = new ResizeObserver(updateDimensions);
    containerObserver.observe(container);
    seqObserver.observe(seq);
    observerCleanups.push(() => containerObserver.disconnect(), () => seqObserver.disconnect());
  } else {
    window.addEventListener("resize", updateDimensions);
    observerCleanups.push(() => window.removeEventListener("resize", updateDimensions));
  }

  const imageCleanups = [];
  const images = seq.querySelectorAll("img");
  if (!images.length) {
    canStartAnimation = true;
    updateDimensions();
  } else {
    let remainingImages = images.length;
    const handleImageLoad = () => {
      remainingImages -= 1;
      if (remainingImages <= 0) {
        canStartAnimation = true;
        updateDimensions();
      }
    };
    images.forEach((image) => {
      if (image.complete) {
        handleImageLoad();
        return;
      }
      image.addEventListener("load", handleImageLoad, { once: true });
      image.addEventListener("error", handleImageLoad, { once: true });
      imageCleanups.push(() => {
        image.removeEventListener("load", handleImageLoad);
        image.removeEventListener("error", handleImageLoad);
      });
    });
  }

  updateDimensions();
  startAnimation();

  return () => {
    const seqSize = isVertical ? seqHeight : seqWidth;
    if (seqSize > 0) {
      logoLoopRuntime.set(loopId, {
        offset,
        velocity,
        seqSize,
        timestamp: performance.now(),
      });
    }
    if (rafId !== null) {
      window.cancelAnimationFrame(rafId);
      rafId = null;
    }
    track.removeEventListener("mouseenter", handleMouseEnter);
    track.removeEventListener("mouseleave", handleMouseLeave);
    observerCleanups.forEach((cleanup) => cleanup());
    imageCleanups.forEach((cleanup) => cleanup());
  };
}

function logoLoopTargetVelocity(speed, direction, isVertical) {
  const magnitude = Math.abs(speed);
  let directionMultiplier;
  if (isVertical) {
    directionMultiplier = direction === "up" ? 1 : -1;
  } else {
    directionMultiplier = direction === "left" ? 1 : -1;
  }
  const speedMultiplier = speed < 0 ? -1 : 1;
  return magnitude * directionMultiplier * speedMultiplier;
}

function clampLogoLoopCopies(copiesNeeded) {
  return Math.min(
    LOGO_LOOP_ANIMATION_CONFIG.MAX_COPIES,
    Math.max(LOGO_LOOP_ANIMATION_CONFIG.MIN_COPIES, copiesNeeded),
  );
}

function loadingTemplate() {
  return `
    <section class="loading-card glass-panel">
      <div class="pulse-dot"></div>
      <h1>正在连接情报流…</h1>
    </section>
  `;
}

function errorTemplate(error) {
  return `
    <section class="error-card glass-panel">
      <h1>数据接口暂不可用</h1>
      <p>${escapeHtml(error)}</p>
      <div style="margin-top:16px">
        <button class="solid-button" type="button" data-action="refresh">重新连接</button>
      </div>
    </section>
  `;
}

function renderHomePage() {
  const status = state.status || {};
  const leaderboard = leaderboardItems();
  const rawItems = rawItemsList();
  const top = leaderboard[0];
  const sources = sourceStats();
  const topics = topicStats(rawItems.length ? rawItems : leaderboard);
  const updated = state.lastLoadedAt ? formatDate(state.lastLoadedAt.toISOString()) : "—";
  const storyCards = leaderboard.slice(1, 7);

  return `
    <section class="news-workbench">
      <header class="workbench-toolbar">
        <div class="workbench-date">${escapeHtml(updated)}</div>
        <div class="workbench-actions">
          <a class="ghost-button" href="/sources" data-route="sources">信源事件</a>
          <button class="solid-button" type="button" data-action="refresh">刷新数据</button>
        </div>
      </header>

      <section class="workbench-hero-copy">
        <div class="hero-copy-main">
          <h1>Today in Tech</h1>
        </div>
        ${renderLogoLoop()}
      </section>

      <section class="workbench-feature-row">
        ${renderTopStoryPanel(top)}
        ${renderSnapshotPanel(status, leaderboard, rawItems, sources)}
      </section>

      <section class="workbench-section">
        <div class="section-title">
          Top Stories
          <span>榜单第 2–7 名</span>
        </div>
        <div class="story-card-grid">
          ${storyCards.map(renderStoryTile).join("") || emptyInline("暂无更多热点")}
        </div>
      </section>

      ${renderInsightsPanel(topics, sources)}
    </section>
  `;
}

function renderTopStoryPanel(item) {
  if (!item) {
    return `
      <article class="top-story-panel glass-panel">
        <span class="story-badge">Top Story</span>
        <h2>暂无榜首事件</h2>
        <p>等待 worker 完成采集后，这里会显示今日最重要的科技新闻。</p>
      </article>
    `;
  }
  const href = safeHref(item.url);
  const imageSrc = safeImageSrc(item.image_url);
  const source = (item.source_names || [])[0] || "未记录来源";
  const topics = (item.topics || []).slice(0, 3).join(" / ") || "no-topic";
  return `
    <article class="top-story-panel glass-panel ${imageSrc ? "has-image" : ""}">
      ${imageSrc ? `
        <a class="top-story-media" href="${href}" target="_blank" rel="noreferrer">
          <img src="${imageSrc}" alt="${escapeAttr(item.image_alt || item.title || "新闻配图")}" loading="eager" decoding="async" fetchpriority="high" referrerpolicy="no-referrer" />
        </a>
      ` : ""}
      <div class="top-story-content">
        <span class="story-badge">Top Story · #${escapeHtml(item.rank ?? 1)}</span>
        <h2><a href="${href}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "未命名事件")}</a></h2>
        <p>${escapeHtml(item.reason || "当前综合分最高的科技事件。")}</p>
        <div class="top-story-footer">
          <div class="story-source-line">
            <span>${escapeHtml(source)}</span>
            <span>${escapeHtml(formatDate(item.updated_at))}</span>
            <span>${escapeHtml(topics)}</span>
          </div>
          <a class="ghost-button" href="${href}" target="_blank" rel="noreferrer">Read More</a>
        </div>
      </div>
    </article>
  `;
}
function renderSnapshotPanel(status, leaderboard, rawItems, sources) {
  const workersText = `${status.workers_enabled ?? "—"}/${status.workers_total ?? "—"}`;
  return `
    <aside class="snapshot-panel glass-panel">
      <h2 class="section-title">Today’s Snapshot <span>实时状态</span></h2>
      <div class="snapshot-list">
        ${snapshotItem("Stories", status.news_events_count ?? leaderboard.length)}
        ${snapshotItem("Raw Items", status.raw_items_count ?? rawItems.length)}
        ${snapshotItem("Sources", sources.length)}
        ${snapshotItem("Workers", workersText)}
      </div>
    </aside>
  `;
}

function renderLogoLoop() {
  return `
    <div class="corner-logoloop">
      ${renderLogoLoopRow({
        items: LOGO_LOOP_TOP_ITEMS,
        loopId: "hero-logo-loop-top",
        direction: "left",
        speed: 54,
        label: "Primary source logos",
        className: "corner-logoloop__row corner-logoloop__row--top",
      })}
      ${renderLogoLoopRow({
        items: LOGO_LOOP_BOTTOM_ITEMS,
        loopId: "hero-logo-loop-bottom",
        direction: "right",
        speed: 42,
        label: "Secondary source logos",
        className: "corner-logoloop__row corner-logoloop__row--bottom",
      })}
    </div>
  `;
}

function renderLogoLoopRow({ items, loopId, direction, speed, label, className }) {
  return `
    <div
      class="logoloop logoloop--horizontal logoloop--fade logoloop--scale-hover ${escapeAttr(className)}"
      data-logo-loop
      data-loop-id="${escapeAttr(loopId)}"
      data-speed="${escapeAttr(speed)}"
      data-direction="${escapeAttr(direction)}"
      data-hover-speed="0"
      data-smooth-tau="0.82"
      style="width: 100%; --logoloop-gap: 52px; --logoloop-logoHeight: 38px;"
      role="region"
      aria-label="${escapeAttr(label)}"
    >
      <div class="logoloop__track">
        <ul class="logoloop__list" role="list">
          ${items.map(renderLogoLoopItem).join("")}
        </ul>
      </div>
    </div>
  `;
}

function renderLogoLoopItem(item) {
  const height = Number(item.height);
  const displayHeight = Number.isFinite(height) && height > 0 ? height * LOGO_LOOP_DISPLAY_SCALE : height;
  const heightStyle = Number.isFinite(height) && height > 0
    ? ` style="--logoloop-logoHeight: ${formatCssNumber(displayHeight)}px;"`
    : "";
  return `
    <li class="logoloop__item" role="listitem"${heightStyle}>
      <a class="logoloop__link" href="${escapeAttr(item.href)}" aria-label="${escapeAttr(item.title)}" target="_blank" rel="noreferrer noopener">
        <img src="${escapeAttr(item.src)}" alt="${escapeAttr(item.title)}" title="${escapeAttr(item.title)}" loading="lazy" decoding="async" draggable="false" />
      </a>
    </li>
  `;
}

function formatCssNumber(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, "");
}

function snapshotItem(label, value) {
  return `
    <div class="snapshot-item">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value ?? "—")}</strong>
    </div>
  `;
}

function renderStoryTile(item) {
  const href = safeHref(item.url);
  const imageSrc = safeImageSrc(item.image_url);
  const primaryTopic = (item.topics || [])[0] || "tech";
  const sources = (item.source_names || []).slice(0, 2).join(" · ") || "来源未记录";
  return `
    <article class="story-tile glass-panel">
      <div class="story-tile-band ${imageSrc ? "has-image" : ""}">
        ${imageSrc ? `<img src="${imageSrc}" alt="${escapeAttr(item.image_alt || item.title || "新闻配图")}" loading="lazy" decoding="async" referrerpolicy="no-referrer" />` : ""}
        <span>${escapeHtml(primaryTopic)}</span>
      </div>
      <div class="story-tile-body">
        <h3><a href="${href}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "未命名事件")}</a></h3>
        <p>${escapeHtml(item.reason || sources)}</p>
        <div class="story-tile-meta">
          <span>${escapeHtml(sources)}</span>
          <strong>${formatScore(item.score)}</strong>
        </div>
      </div>
    </article>
  `;
}
function renderInsightsPanel(topics, sources) {
  const topTopics = topics.slice(0, 5);
  return `
    <section class="insights-panel glass-panel">
      <div>
        <h2 class="section-title">Insights <span>主题与信源分布</span></h2>
        <div class="insight-bars">
          ${topTopics.map((topic) => {
            const percent = Math.max(4, Math.round((topic.count / Math.max(1, topTopics[0]?.count || 1)) * 100));
            return `
              <div class="insight-bar">
                <span>${escapeHtml(topic.key)}</span>
                <i><b style="width:${percent}%"></b></i>
                <em>${escapeHtml(topic.count)}</em>
              </div>
            `;
          }).join("") || emptyInline("暂无主题分布")}
        </div>
      </div>
      <div>
        <h2 class="section-title">信源密度 <span>${sources.length} 个活跃信源</span></h2>
        ${renderBarList(sources.slice(0, 8).map((source) => ({
          label: source.name,
          value: source.count,
          max: sources[0]?.count || 1,
        })))}
      </div>
    </section>
  `;
}

function renderHero(item) {
  const topics = (item.topics || []).slice(0, 6).map((topic) => `<span class="chip">${escapeHtml(topic)}</span>`).join("");
  const href = safeHref(item.url);
  const imageSrc = safeImageSrc(item.image_url);
  return `
    <article class="hero-card glass-panel ${imageSrc ? "has-image" : ""}">
      ${imageSrc ? `
        <a class="hero-image" href="${href}" target="_blank" rel="noreferrer">
          <img src="${imageSrc}" alt="${escapeAttr(item.image_alt || item.title || "新闻配图")}" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
        </a>
      ` : ""}
      <div class="hero-copy">
        <div class="hero-meta">
          <span class="chip good">#${escapeHtml(item.rank ?? 1)} · score ${formatScore(item.score)}</span>
          <span class="chip">${escapeHtml(item.source_count ?? "—")} sources</span>
          ${topics}
        </div>
        <h2 class="hero-title"><a href="${href}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "未命名事件")}</a></h2>
        <p class="hero-reason">${escapeHtml(item.reason || "该事件在多个信源中出现，综合分位于当前榜首。")}</p>
        <div class="hero-footer">
          <div class="news-meta">
            ${(item.source_names || []).slice(0, 6).map((name) => `<span>${escapeHtml(name)}</span>`).join("")}
          </div>
          <a class="ghost-button" href="${href}" target="_blank" rel="noreferrer">打开原文</a>
        </div>
      </div>
    </article>
  `;
}
function renderNewsRow(item) {
  const href = safeHref(item.url);
  const imageSrc = safeImageSrc(item.image_url);
  const sources = (item.source_names || []).slice(0, 4).join(" · ");
  return `
    <article class="news-row ${imageSrc ? "has-image" : ""}">
      <div class="rank-num">#${escapeHtml(item.rank ?? "—")}</div>
      ${imageSrc ? `
        <a class="news-thumb" href="${href}" target="_blank" rel="noreferrer">
          <img src="${imageSrc}" alt="${escapeAttr(item.image_alt || item.title || "新闻配图")}" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
        </a>
      ` : ""}
      <div>
        <h3 class="news-title"><a href="${href}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "未命名事件")}</a></h3>
        <div class="news-meta">
          <span>${escapeHtml(sources || "来源未记录")}</span>
          <span>${escapeHtml((item.topics || []).slice(0, 4).join(" / ") || "no-topic")}</span>
          <span>${escapeHtml(formatDate(item.updated_at))}</span>
        </div>
      </div>
      <div class="score-pill">${formatScore(item.score)}</div>
    </article>
  `;
}
function renderSourcesPage() {
  const sources = sourceStats();
  const selected = sources.find((source) => source.id === state.selectedSourceId) || sources[0];
  const selectedId = selected?.id || "";
  const filtered = filterRawItems(rawItemsList(), selectedId);
  const allCount = rawItemsList().length;

  return `
    <section class="page-header">
      <div>
        <h1 class="page-title">信源事件详情</h1>
      </div>
      <span class="page-time">${sources.length} 个信源 · ${allCount} 条 RawItem</span>
    </section>

    <section class="sources-layout">
      <aside class="source-list-panel glass-panel">
        <h2 class="section-title">信源列表 <span>${sources.length}</span></h2>
        <div class="source-list">
          ${sources.map((source) => renderSourceButton(source, selectedId)).join("") || emptyInline("暂无信源")}
        </div>
      </aside>

      <section class="source-stream-panel glass-panel">
        <h2 class="section-title">${escapeHtml(selected?.name || "全部事件")} <span>${filtered.length} 条</span></h2>
        <div class="raw-list">
          ${filtered.slice(0, 120).map(renderRawCard).join("") || emptyInline("暂无原始事件")}
        </div>
      </section>

      <aside class="source-detail-panel glass-panel">
        ${selected ? renderSourceDetail(selected, filtered) : emptyInline("暂无信源摘要")}
      </aside>
    </section>
  `;
}

function renderSourceButton(source, selectedId) {
  const active = source.id === selectedId;
  return `
    <button class="source-button ${active ? "active" : ""}" type="button" data-source-id="${escapeAttr(source.id)}" aria-pressed="${active ? "true" : "false"}" title="${escapeAttr(`${source.type || "unknown"} · ${source.count} 条`)}">
      <strong>${escapeHtml(source.name)}</strong>
      <span class="source-count-badge" aria-label="${source.count} 条">${source.count}</span>
    </button>
  `;
}

function renderRawCard(item) {
  const href = safeHref(item.url);
  const metadata = item.metadata || {};
  const imageSrc = safeImageSrc(imageUrlFromRaw(item));
  const meta = [
    item.source_name,
    item.source_type,
    item.worker_id,
    formatDate(item.published_at),
    metadata.subreddit ? `r/${metadata.subreddit}` : "",
    Array.isArray(metadata.view_hits) && metadata.view_hits.length ? `views ${metadata.view_hits.join(",")}` : "",
    metadata.reddit_score != null ? `reddit ${metadata.reddit_score}` : "",
    metadata.image_source ? `image ${metadata.image_source}` : "",
  ].filter(Boolean);

  return `
    <article class="raw-card ${imageSrc ? "has-image" : ""}">
      ${imageSrc ? `
        <a class="raw-thumb" href="${href}" target="_blank" rel="noreferrer">
          <img src="${imageSrc}" alt="${escapeAttr(item.title || "新闻配图")}" loading="lazy" decoding="async" referrerpolicy="no-referrer" />
        </a>
      ` : ""}
      <div class="raw-card-copy">
        <h3 class="raw-title"><a href="${href}" target="_blank" rel="noreferrer">${escapeHtml(item.title || "未命名条目")}</a></h3>
        <div class="raw-meta">${meta.map((x) => `<span>${escapeHtml(x)}</span>`).join("")}</div>
        ${item.raw_text ? `<p class="raw-text">${escapeHtml(stripHtml(item.raw_text))}</p>` : ""}
        <div class="topic-cloud">
          ${(item.topics || []).slice(0, 8).map((topic) => `<span class="chip">${escapeHtml(topic)}</span>`).join("")}
        </div>
      </div>
    </article>
  `;
}
function renderSourceDetail(source, filtered) {
  const topics = Array.from(source.topics.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  const latest = source.latest ? formatDate(source.latest) : "—";
  const workers = Array.from(source.workers).join(" · ") || "—";
  const views = Array.from(source.views.entries()).sort((a, b) => b[1] - a[1]);

  return `
    <h2 class="section-title">信源摘要 <span>${escapeHtml(source.id)}</span></h2>
    <div class="detail-block">
      <div class="detail-label">名称</div>
      <div class="detail-value">${escapeHtml(source.name)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">类型 / Worker</div>
      <div class="detail-value">${escapeHtml(source.type || "—")} · ${escapeHtml(workers)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">条目</div>
      <div class="detail-value">${source.count} 条总量 · 当前显示 ${filtered.length} 条</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">最近发布时间</div>
      <div class="detail-value">${escapeHtml(latest)}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">主题</div>
      <div class="topic-cloud">
        ${topics.map(([topic, count]) => `<span class="chip">${escapeHtml(topic)} · ${count}</span>`).join("") || "—"}
      </div>
    </div>
    ${views.length ? `
      <div class="detail-block">
        <div class="detail-label">Reddit 四路视角</div>
        <div class="topic-cloud">
          ${views.map(([view, count]) => `<span class="chip good">${escapeHtml(view)} · ${count}</span>`).join("")}
        </div>
      </div>
    ` : ""}
  `;
}

function renderOpsPage() {
  const status = state.status || {};
  const service = status.service || {};
  const workers = Array.isArray(status.workers) ? status.workers : [];

  return `
    <section class="page-header">
      <div>
        <h1 class="page-title">运维监控</h1>
      </div>
      <span class="page-time">${status.workers_due ?? 0} 个 Worker 到期</span>
    </section>

    <section class="ops-grid">
      <div class="ops-panel glass-panel">
        <h2 class="section-title">Worker 状态 <span>${workers.length}</span></h2>
        <div class="worker-grid">
          ${workers.map(renderWorkerCard).join("") || emptyInline("暂无 worker 状态")}
        </div>
      </div>

      <aside class="side-stack">
        <section class="ops-panel glass-panel">
          <h2 class="section-title">服务运行时 <span>${escapeHtml(service.include_github ? "github on" : "github off")}</span></h2>
          <div class="kv-list">
            ${kvRow("poll_seconds", service.poll_seconds)}
            ${kvRow("max_workers", service.max_workers)}
            ${kvRow("leaderboard_top", service.leaderboard_top)}
            ${kvRow("llm_enabled", service.llm_enabled ? "true" : "false")}
            ${kvRow("llm_scores", service.llm_scores_count ?? "—")}
            ${kvRow("last_cycle_at", formatDate(service.last_cycle_at))}
            ${kvRow("last_error", service.last_error || "—")}
            ${kvRow("runtime_dir", service.runtime_dir)}
            ${kvRow("config_dir", service.config_dir)}
          </div>
        </section>

        <section class="ops-panel glass-panel">
          <h2 class="section-title">手动采集 <span>POST /api/run-once</span></h2>
          <p class="run-note">只运行当前到期的 Worker。若没有到期任务，接口会返回“无到期 Worker”。</p>
          <button class="solid-button" type="button" data-action="run-once" ${state.running ? "disabled" : ""}>${state.running ? "采集中…" : "运行一轮到期 Worker"}</button>
        </section>

        <section class="ops-panel glass-panel">
          <h2 class="section-title">最近一轮结果 <span>last_cycle_result</span></h2>
          <pre class="json-pre">${escapeHtml(JSON.stringify(service.last_cycle_result || {}, null, 2))}</pre>
        </section>
      </aside>
    </section>
  `;
}

function renderWorkerCard(worker) {
  const failures = Number(worker.consecutive_failures || 0);
  const due = Number(worker.due_in_seconds || 0);
  const statusClass = failures > 0 ? "fail" : due <= 0 ? "due" : "ok";
  const statusText = failures > 0 ? `${failures} FAIL` : due <= 0 ? "DUE" : "OK";
  return `
    <article class="worker-card">
      <div class="worker-head">
        <strong>${escapeHtml(worker.worker_id || "unknown-worker")}</strong>
        <span class="status-dot ${statusClass}">${escapeHtml(statusText)}</span>
      </div>
      <div class="worker-meta">
        <span>${worker.enabled ? "enabled" : "disabled"}</span>
        <span>${due <= 0 ? "已到期" : `${formatDuration(due)} 后到期`}</span>
        <span>last ${escapeHtml(formatDate(worker.last_success_at))}</span>
      </div>
      ${worker.last_error ? `<p class="worker-error">${escapeHtml(worker.last_error)}</p>` : ""}
    </article>
  `;
}

function metricCard(label, value, note) {
  return `
    <article class="metric-card glass-panel">
      <div class="metric-label">${escapeHtml(label)}</div>
      <div class="metric-value">${escapeHtml(value ?? "—")}</div>
      <div class="metric-note">${escapeHtml(note || "—")}</div>
    </article>
  `;
}

function renderBarList(rows) {
  if (!rows.length) return emptyInline("暂无分布数据");
  return `
    <div class="bar-list">
      ${rows.map((row) => {
        const percent = Math.max(3, Math.round((Number(row.value || 0) / Math.max(1, row.max)) * 100));
        return `
          <div class="bar-row">
            <span class="bar-label" title="${escapeAttr(row.label)}">${escapeHtml(row.label)}</span>
            <span class="bar-track"><span class="bar-fill" style="width:${percent}%"></span></span>
            <span>${escapeHtml(row.value)}</span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function kvRow(key, value) {
  return `
    <div class="kv-row">
      <div class="kv-key">${escapeHtml(key)}</div>
      <div class="kv-value">${escapeHtml(value ?? "—")}</div>
    </div>
  `;
}

function emptyBlock(title, text) {
  return `
    <section class="empty-state glass-panel">
      <h2>${escapeHtml(title)}</h2>
      <p>${escapeHtml(text || "")}</p>
    </section>
  `;
}

function emptyInline(text) {
  return `<div class="empty-state inline-empty"><p>${escapeHtml(text)}</p></div>`;
}

function leaderboardItems() {
  const items = Array.isArray(state.leaderboard?.items) ? state.leaderboard.items : EMPTY_ITEMS;
  if (derivedCache.leaderboardRef !== items) {
    derivedCache.leaderboardRef = items;
    derivedCache.leaderboardItems = items.slice().sort((a, b) => {
      const rankA = Number.isFinite(Number(a.rank)) ? Number(a.rank) : Number.MAX_SAFE_INTEGER;
      const rankB = Number.isFinite(Number(b.rank)) ? Number(b.rank) : Number.MAX_SAFE_INTEGER;
      return rankA - rankB || Number(b.score || 0) - Number(a.score || 0);
    });
  }
  return derivedCache.leaderboardItems || EMPTY_ITEMS;
}

function rawItemsList() {
  const items = Array.isArray(state.raw?.items) ? state.raw.items : EMPTY_ITEMS;
  if (derivedCache.rawRef !== items) {
    derivedCache.rawRef = items;
    derivedCache.rawItems = items;
  }
  return derivedCache.rawItems || EMPTY_ITEMS;
}

function sourceStats() {
  const rawItems = rawItemsList();
  if (derivedCache.sourceRawRef === rawItems && derivedCache.sourceStats) {
    return derivedCache.sourceStats;
  }

  const map = new Map();
  for (const item of rawItems) {
    const id = sourceIdentity(item);
    if (!map.has(id)) {
      map.set(id, {
        id,
        name: item.source_name || id,
        type: item.source_type || "",
        count: 0,
        latest: "",
        topics: new Map(),
        workers: new Set(),
        views: new Map(),
      });
    }
    const source = map.get(id);
    source.count += 1;
    source.type = source.type || item.source_type || "";
    if (item.worker_id) source.workers.add(item.worker_id);
    if (!source.latest || new Date(item.published_at || 0) > new Date(source.latest || 0)) {
      source.latest = item.published_at || source.latest;
    }
    for (const topic of item.topics || []) {
      source.topics.set(topic, (source.topics.get(topic) || 0) + 1);
    }
    for (const view of item.metadata?.view_hits || []) {
      source.views.set(view, (source.views.get(view) || 0) + 1);
    }
  }
  derivedCache.sourceRawRef = rawItems;
  derivedCache.sourceStats = Array.from(map.values()).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  return derivedCache.sourceStats;
}

function sourceIdentity(item) {
  return item?.source_id || item?.source_name || "unknown";
}

function ensureSelectedSource() {
  if (state.route !== "sources") return;
  const sources = sourceStats();
  if (!sources.length) {
    state.selectedSourceId = "";
    return;
  }
  if (!state.selectedSourceId || !sources.some((source) => source.id === state.selectedSourceId)) {
    state.selectedSourceId = sources[0].id;
  }
}

function filterRawItems(items, sourceId) {
  return items.filter((item) => {
    const sourceOk = !sourceId || sourceIdentity(item) === sourceId;
    return sourceOk;
  });
}

function topicStats(items) {
  const map = new Map();
  for (const item of items) {
    for (const topic of item.topics || []) {
      map.set(topic, (map.get(topic) || 0) + 1);
    }
  }
  return Array.from(map, ([key, count]) => ({ key, count })).sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function safeHref(url) {
  const value = String(url || "");
  if (/^https?:\/\//i.test(value)) return escapeAttr(value);
  return "#";
}

function safeImageSrc(url) {
  const value = String(url || "");
  if (/^https?:\/\//i.test(value)) return escapeAttr(value);
  return "";
}

function imageUrlFromRaw(item) {
  return item?.metadata?.image_url || "";
}

function stripHtml(value) {
  return String(value || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function formatScore(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number >= 100 ? number.toFixed(0) : number.toFixed(1);
}

function formatDate(value) {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds || 0));
  if (value < 60) return `${Math.round(value)}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}

document.addEventListener("click", (event) => {
  const routeLink = event.target.closest?.("[data-route]");
  if (routeLink) {
    event.preventDefault();
    navigate(routeLink.dataset.route || "home");
    return;
  }

  const sourceButton = event.target.closest?.("[data-source-id]");
  if (sourceButton) {
    state.selectedSourceId = sourceButton.dataset.sourceId || "";
    render();
    return;
  }

  const action = event.target.closest?.("[data-action]")?.dataset.action;
  if (action === "refresh") {
    refreshData({ keepLoading: true });
  } else if (action === "run-once") {
    runOnce();
  }
});

window.addEventListener("popstate", () => {
  state.route = routeFromPath(location.pathname);
  ensureSelectedSource();
  render();
});

refreshButton?.addEventListener("click", () => refreshData({ keepLoading: true }));

refreshData();


