/* ===================================================================
   Page Évolution — viz des tendances dans le temps depuis Postgres.
   Lit data/analytics/evolution.json généré par `python -m server.cli db-export`
   à chaque run du pipeline CI.
   =================================================================== */

const DATA_URL = "data/analytics/evolution.json";

/* ----- Helpers DOM ----- */
const $ = (sel) => document.querySelector(sel);

const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
};

const fmtRelative = (iso) => {
  if (!iso) return "—";
  const dt = new Date(iso);
  const min = Math.floor((Date.now() - dt) / 60000);
  if (min < 60) return `il y a ${min} min`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `il y a ${hr} h`;
  return `il y a ${Math.floor(hr / 24)} j`;
};

const fmtSigned = (n) => (n > 0 ? `+${n}` : String(n));

const truncate = (s, n = 100) =>
  s && s.length > n ? s.slice(0, n - 1) + "…" : s || "";

const TOPIC_KIND_LABEL = {
  entity: "entité",
  cluster: "cluster",
  category: "catégorie",
};

/* ----- 1. TOPICS QUI MONTENT ----- */

const renderTopics = (topics) => {
  const tbody = $("#evo-topics-body");
  const table = $("#evo-topics-table");
  const empty = $("#evo-empty-topics");

  if (!topics || topics.length === 0) {
    empty.hidden = false;
    return;
  }

  table.hidden = false;
  for (const [i, t] of topics.entries()) {
    const isNew = t.prev_count === 0;
    const trClass =
      t.delta > 0
        ? "evo-row--up"
        : t.delta < 0
          ? "evo-row--down"
          : "evo-row--flat";

    tbody.appendChild(
      h(
        "tr",
        { class: trClass },
        h("td", { class: "evo-rank" }, String(i + 1).padStart(2, "0")),
        h(
          "td",
          { class: "evo-topic" },
          h("strong", {}, t.topic_label || t.topic_name),
        ),
        h(
          "td",
          { class: "evo-kind" },
          h(
            "span",
            { class: `evo-kind-pill evo-kind-pill--${t.topic_kind}` },
            TOPIC_KIND_LABEL[t.topic_kind] || t.topic_kind,
          ),
        ),
        h("td", { class: "ta-right evo-current" }, String(t.current_count)),
        h(
          "td",
          { class: "ta-right evo-delta" },
          isNew
            ? h("span", { class: "evo-badge-new" }, "NEW")
            : h("span", {}, fmtSigned(t.delta)),
        ),
        h(
          "td",
          { class: "ta-right evo-pct" },
          isNew
            ? "—"
            : t.pct_change != null
              ? `${fmtSigned(t.pct_change)} %`
              : "—",
        ),
      ),
    );
  }
};

/* ----- 2. SUJETS PERSISTANTS ----- */

const renderSujets = (sujets) => {
  const tbody = $("#evo-sujets-body");
  const table = $("#evo-sujets-table");
  const empty = $("#evo-empty-sujets");

  if (!sujets || sujets.length === 0) {
    empty.hidden = false;
    return;
  }

  table.hidden = false;
  for (const s of sujets) {
    const scoreCls =
      s.score_delta > 0
        ? "evo-score-delta--up"
        : s.score_delta < 0
          ? "evo-score-delta--down"
          : "";

    tbody.appendChild(
      h(
        "tr",
        {},
        h(
          "td",
          { class: "evo-sujet-title" },
          s.msn_url
            ? h(
                "a",
                {
                  href: s.msn_url,
                  target: "_blank",
                  rel: "noopener noreferrer",
                },
                truncate(s.title, 100),
              )
            : truncate(s.title, 100),
        ),
        h(
          "td",
          { class: "ta-center" },
          h("strong", {}, `×${s.appearances}`),
        ),
        h("td", { class: "ta-right" }, String(s.max_score)),
        h(
          "td",
          { class: `ta-right evo-score-delta ${scoreCls}` },
          fmtSigned(s.score_delta),
        ),
        h(
          "td",
          { class: "evo-cat" },
          (s.category || "").split("/").filter(Boolean).slice(-2).join(" / ") ||
            "—",
        ),
      ),
    );
  }
};

/* ----- 3. HEATMAP CATÉGORIES × SOURCES ----- */

const CATEGORIES = [
  "politique",
  "international",
  "economie",
  "tech",
  "sport",
  "people",
  "science",
  "sante",
  "societe",
  "lifestyle",
];

const SOURCES_HEATMAP = [
  "discover",
  "gnews",
  "reddit",
  "youtube",
  "trends",
  "msn",
];

const renderHeatmap = (rows) => {
  const container = $("#evo-heatmap");
  const empty = $("#evo-empty-heatmap");

  if (!rows || rows.length === 0) {
    empty.hidden = false;
    return;
  }

  // Index par (cat, src) pour lookup rapide
  const byKey = {};
  for (const r of rows) {
    byKey[`${r.category}|${r.source}`] = r;
  }

  // Max delta absolu pour normaliser l'intensité de couleur
  const maxAbs = Math.max(
    1,
    ...rows.map((r) => Math.abs(r.delta)),
  );

  const grid = h("div", { class: "evo-heatmap__grid" });

  // Header sources
  grid.appendChild(h("div", { class: "evo-heatmap__corner" }, ""));
  for (const src of SOURCES_HEATMAP) {
    grid.appendChild(
      h(
        "div",
        { class: "evo-heatmap__col-head", "data-source-color": src },
        src.toUpperCase(),
      ),
    );
  }

  // Body : 1 ligne par catégorie
  for (const cat of CATEGORIES) {
    grid.appendChild(h("div", { class: "evo-heatmap__row-head" }, cat));
    for (const src of SOURCES_HEATMAP) {
      const r = byKey[`${cat}|${src}`];
      const delta = r ? r.delta : 0;
      const current = r ? r.current_count : 0;
      const intensity = Math.min(1, Math.abs(delta) / maxAbs);
      // Couleur : rouge si delta > 0, bleu froid si delta < 0, gris si 0
      let bg = "transparent";
      if (delta > 0) {
        bg = `rgba(245, 0, 0, ${0.1 + 0.7 * intensity})`;
      } else if (delta < 0) {
        bg = `rgba(0, 164, 239, ${0.1 + 0.5 * intensity})`;
      }
      grid.appendChild(
        h(
          "div",
          {
            class: "evo-heatmap__cell",
            style: `background: ${bg}`,
            title: `${cat} × ${src} : ${current} items (Δ ${fmtSigned(delta)})`,
          },
          h("span", { class: "evo-heatmap__cell-current" }, String(current)),
          delta !== 0
            ? h(
                "span",
                { class: "evo-heatmap__cell-delta" },
                fmtSigned(delta),
              )
            : null,
        ),
      );
    }
  }

  container.appendChild(grid);
};

/* ----- 4. PULSE DES SOURCES (sparklines SVG) ----- */

const SOURCE_COLORS = {
  discover: "#00FF00",
  gnews: "#4285F4",
  reddit: "#FF4500",
  youtube: "#FF0033",
  trends: "#FBBC04",
  wikimedia: "#FFFFFF",
  x_trends: "#00FFFF",
  msn: "#00A4EF",
};

const renderSparkline = (points, color = "#fff") => {
  if (!points || points.length < 2) {
    return h(
      "div",
      { class: "evo-sparkline evo-sparkline--empty" },
      "pas assez de points",
    );
  }
  const w = 280;
  const ht = 50;
  const max = Math.max(1, ...points.map((p) => p.count));
  const min = Math.min(...points.map((p) => p.count));
  const range = Math.max(1, max - min);
  const step = w / (points.length - 1);
  const pts = points
    .map((p, i) => {
      const x = i * step;
      const y = ht - ((p.count - min) / range) * (ht - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const svg = `
    <svg viewBox="0 0 ${w} ${ht}" xmlns="http://www.w3.org/2000/svg"
         preserveAspectRatio="none" class="evo-sparkline__svg">
      <polyline points="${pts}" fill="none" stroke="${color}"
                stroke-width="1.5" stroke-linejoin="round" />
    </svg>`;
  const div = document.createElement("div");
  div.className = "evo-sparkline";
  div.innerHTML = svg;
  return div;
};

const renderSources = (timeline) => {
  const container = $("#evo-sources");
  const empty = $("#evo-empty-sources");

  const sources = Object.keys(timeline || {});
  if (sources.length === 0) {
    empty.hidden = false;
    return;
  }

  for (const src of sources.sort()) {
    const points = timeline[src];
    const latest = points[points.length - 1];
    const oldest = points[0];
    const delta = latest && oldest ? latest.count - oldest.count : 0;

    const card = h(
      "div",
      { class: "evo-source-card" },
      h(
        "div",
        { class: "evo-source-card__head" },
        h(
          "span",
          { class: "evo-source-card__name", "data-source-color": src },
          src,
        ),
        h(
          "span",
          { class: "evo-source-card__current" },
          latest ? `${latest.count} items` : "—",
        ),
      ),
      renderSparkline(points, SOURCE_COLORS[src] || "#fff"),
      h(
        "div",
        { class: "evo-source-card__foot" },
        `${points.length} snapshots · Δ 7j: ${fmtSigned(delta)}`,
      ),
    );
    container.appendChild(card);
  }
};

/* ----- Mount ----- */

const mount = async () => {
  let payload;
  try {
    const r = await fetch(DATA_URL, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    payload = await r.json();
  } catch (err) {
    $("#evo-eyebrow").textContent = "Évolution · données indisponibles";
    $("#evo-empty-topics").hidden = false;
    $("#evo-empty-sujets").hidden = false;
    $("#evo-empty-heatmap").hidden = false;
    $("#evo-empty-sources").hidden = false;
    return;
  }

  if (!payload.available) {
    $("#evo-eyebrow").textContent = `Évolution · ${payload.reason || "indisponible"}`;
    $("#evo-empty-topics").hidden = false;
    $("#evo-empty-sujets").hidden = false;
    $("#evo-empty-heatmap").hidden = false;
    $("#evo-empty-sources").hidden = false;
    return;
  }

  $("#evo-eyebrow").textContent = `Évolution · généré ${fmtRelative(payload.generated_at)}`;

  renderTopics(payload.topics_24h);
  renderSujets(payload.sujets_persistance);
  renderHeatmap(payload.category_momentum_24h);
  renderSources(payload.source_timeline_7d);
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
