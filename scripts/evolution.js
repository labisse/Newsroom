/* ============================================================
   EDITORIAL SIGNAL — Évolution (design Claude, vanilla)
   4 sections : topics qui montent · sujets persistants ·
   heatmap cat × source · pulse sources.
   ============================================================ */

/* ---------- DOM helpers ---------- */
const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k === "style" && typeof v === "object") {
      for (const [sk, sv] of Object.entries(v)) {
        if (sv != null) el.style.setProperty(sk.startsWith("--") ? sk : kebab(sk), String(sv));
      }
    } else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
};
const kebab = (s) => s.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());

const svgEl = (paths, w = 18, hp = 18, sw = 2) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", String(sw));
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("width", String(w));
  s.setAttribute("height", String(hp));
  s.innerHTML = paths;
  return s;
};

/* ---------- Icons ---------- */
const Ic = {
  up: () => svgEl('<path d="m6 15 6-6 6 6"/>', 11, 11, 2.2),
  down: () => svgEl('<path d="m6 9 6 6 6-6"/>', 11, 11, 2.2),
  flat: () => svgEl('<path d="M5 12h14"/>', 11, 11, 2.2),
  trend: () => svgEl('<path d="m3 17 6-6 4 4 8-8"/><path d="M17 7h4v4"/>'),
  radar: () => svgEl(
    '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 19 5"/>',
  ),
  flame: () => svgEl(
    '<path d="M12 3c1 3 4 4 4 8a4 4 0 0 1-8 0c0-1 .5-2 1-2.5C9 11 12 9 12 3Z"/>',
  ),
  pulse: () => svgEl('<path d="M3 12h4l2-6 4 12 2-6h6"/>'),
};

const CAT_ICON = {
  politique: () => svgEl(
    '<path d="M3 22h18M5 10v9M9 10v9M15 10v9M19 10v9M3 6l9-4 9 4v3H3V6Z"/>',
  ),
  international: () => svgEl(
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  ),
  economie: () => svgEl(
    '<circle cx="8" cy="8" r="5"/><path d="M11 12.5a5 5 0 1 0 5.5 6.5"/><path d="M5.5 8.5h5"/>',
  ),
  tech: () => svgEl(
    '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  ),
  sport: () => svgEl(
    '<path d="M7 4h10v6a5 5 0 0 1-10 0V4Z"/><path d="M7 7H4a2 2 0 0 0 0 4h3M17 7h3a2 2 0 0 1 0 4h-3"/><path d="M10 17h4M12 14v3M8 21h8"/>',
  ),
  people: () => svgEl(
    '<path d="M12 3l1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8L12 3Z"/>',
  ),
  science: () => svgEl(
    '<circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="10" ry="4.5"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(-60 12 12)"/>',
  ),
  sante: () => svgEl(
    '<path d="M12 20s-7-4.5-9-9a4.5 4.5 0 0 1 9-2 4.5 4.5 0 0 1 9 2c-2 4.5-9 9-9 9Z"/>',
  ),
  societe: () => svgEl(
    '<circle cx="9" cy="8" r="3.5"/><path d="M3 21c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="9" r="3"/><path d="M14 21c0-2 2-4 6-4"/>',
  ),
  lifestyle: () => svgEl(
    '<path d="M3 21c0-9 7-16 18-17 0 11-7 17-18 17"/><path d="M3 21c5-5 9-9 14-12"/>',
  ),
};

const SRC_GLYPH = {
  discover: () => svgEl(
    '<circle cx="12" cy="12" r="8"/><path d="m9 15 1.5-4.5L15 9l-1.5 4.5L9 15Z" fill="currentColor" stroke="none"/>',
  ),
  gnews: () => svgEl('<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 12h8M8 15h5"/>'),
  trends: () => svgEl('<path d="m4 16 5-5 3 3 7-7"/><path d="M16 7h4v4"/>'),
  wiki: () => svgEl('<path d="M3 7 7 17 10.5 9 14 17 21 7"/>'),
  msn: () => svgEl('<path d="M4 18V7l4 6 4-6 4 6 4-6v11"/>'),
  x: () => svgEl('<path d="M5 5l14 14M19 5 5 19"/>'),
  reddit: () => svgEl(
    '<circle cx="12" cy="13" r="7"/><circle cx="12" cy="4" r="1.4"/><path d="M12 5.5V9"/><circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none"/><path d="M9.5 16c1.5 1 3.5 1 5 0"/>',
  ),
  youtube: () => svgEl(
    '<rect x="3" y="6" width="18" height="12" rx="3"/><path d="m10.5 9.5 4 2.5-4 2.5Z" fill="currentColor" stroke="none"/>',
  ),
};

const HUE = {
  indigo: "#818CF8", pink: "#F472B6", emerald: "#34D399",
  purple: "#C084FC", amber: "#FBBF24", blue: "#60A5FA", red: "#FB7185",
};

const SRC_HUE = {
  discover: "indigo", gnews: "blue", msn: "indigo", trends: "emerald",
  wiki: "purple", youtube: "red", x: "blue", reddit: "amber",
};

const TYPE_META = {
  entity: { label: "Entité", hue: "emerald" },
  cluster: { label: "Cluster", hue: "purple" },
  category: { label: "Catégorie", hue: "blue" },
};

/* ---------- helpers viz ---------- */

const fmtDelta = (d) => (d > 0 ? "+" : "") + d;

const Delta = (d) => {
  if (d === 0)
    return h("span", { class: "evo-delta flat" }, Ic.flat(), "0");
  const up = d > 0;
  return h(
    "span",
    { class: "evo-delta " + (up ? "up" : "down") },
    up ? Ic.up() : Ic.down(),
    fmtDelta(d),
  );
};

const Sparkline = (data, opts = {}) => {
  const w = opts.w || 120;
  const ht = opts.h || 34;
  const color = opts.color || "var(--brand)";
  const area = opts.area !== false;
  const strokeW = opts.strokeW || 1.7;
  const dot = opts.dot !== false;

  if (!data || data.length === 0) {
    const wrap = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    wrap.setAttribute("width", String(w));
    wrap.setAttribute("height", String(ht));
    return wrap;
  }

  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (data.length === 1 ? 0.5 : i / (data.length - 1)) * w;
    const y = ht - ((v - min) / range) * (ht - 5) - 3;
    return [x, y];
  });
  const line = pts
    .map((pt, i) => (i ? "L" : "M") + pt[0].toFixed(1) + " " + pt[1].toFixed(1))
    .join(" ");
  const areaPath = line + ` L ${w} ${ht} L 0 ${ht} Z`;
  const id = "sg" + Math.random().toString(36).slice(2, 8);
  const last = pts[pts.length - 1];
  const flat = max === min;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", String(w));
  svg.setAttribute("height", String(ht));
  svg.setAttribute("viewBox", `0 0 ${w} ${ht}`);
  svg.style.display = "block";
  svg.setAttribute("preserveAspectRatio", "none");

  let inner = "";
  if (area && !flat) {
    inner += `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity="0.26"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs><path d="${areaPath}" fill="url(#${id})"/>`;
  }
  inner += `<path d="${line}" fill="none" stroke="${flat ? "var(--fg-faint)" : color}" stroke-width="${strokeW}" stroke-linecap="round" stroke-linejoin="round"/>`;
  if (dot) {
    inner += `<circle cx="${last[0]}" cy="${last[1]}" r="2.4" fill="${flat ? "var(--fg-faint)" : color}"/>`;
  }
  svg.innerHTML = inner;
  return svg;
};

const fmtAgo = (iso) => {
  if (!iso) return "—";
  try {
    const dt = new Date(iso);
    const min = Math.floor((Date.now() - dt.getTime()) / 60000);
    if (min < 1) return "à l'instant";
    if (min < 60) return `il y a ${min} min`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `il y a ${hr} h`;
    return `il y a ${Math.floor(hr / 24)} j`;
  } catch {
    return "—";
  }
};

/* ---------- state ---------- */
const state = {
  evo: null,
  loading: true,
};

/* ---------- adapters depuis evolution.json ---------- */

/** Pour chaque topic du rising, on n'a que current_count / prev_count.
 *  On simule un mini-spark (2-3 points) basé sur prev → current pour
 *  illustrer. Plus tard : passer ces données via une vraie série
 *  historique stockée en DB. */
const buildRisingRows = (evo) => {
  const topics = (evo.topics_24h || []).slice(0, 21);
  return topics.map((t) => {
    const isNew = t.prev_count === 0;
    const spark = isNew
      ? [0, 0, 0, Math.max(1, Math.round(t.current_count / 2)), t.current_count]
      : [
          t.prev_count,
          Math.round((t.prev_count + t.current_count) / 2),
          t.current_count,
        ];
    return {
      topic: t.topic_label || t.topic_name,
      type: t.topic_kind, // entity | cluster | category
      articles: t.current_count,
      delta: isNew ? "new" : t.current_count - t.prev_count,
      spark,
      pct:
        isNew
          ? "new"
          : t.pct_change != null
            ? `${t.pct_change > 0 ? "+" : ""}${t.pct_change}%`
            : "—",
    };
  });
};

const buildPersistent = (evo) => {
  const sujets = (evo.sujets_persistance || []).slice(0, 9);
  return sujets.map((s) => {
    const status =
      s.score_delta > 0 ? "up" : s.score_delta < 0 ? "down" : "flat";
    return {
      topic: s.title,
      type: "cluster", // pas dispo, on assume cluster pour le badge
      app: s.appearances || 0,
      total: Math.max(s.appearances || 0, 4),
      score: [s.first_score || 0, s.max_score || 0, s.last_score || 0],
      status,
    };
  });
};

/** Heatmap : on prend les category_momentum_24h et on construit une
 *  grille 10cats × 6sources avec items_count comme valeur. */
const HEAT_COLS = ["discover", "gnews", "reddit", "youtube", "trends", "msn"];
const HEAT_ROWS = [
  { cat: "Politique", key: "politique", icon: "politique" },
  { cat: "International", key: "international", icon: "international" },
  { cat: "Économie", key: "economie", icon: "economie" },
  { cat: "Tech", key: "tech", icon: "tech" },
  { cat: "Sport", key: "sport", icon: "sport" },
  { cat: "People", key: "people", icon: "people" },
  { cat: "Science", key: "science", icon: "science" },
  { cat: "Santé", key: "sante", icon: "sante" },
  { cat: "Société", key: "societe", icon: "societe" },
  { cat: "Lifestyle", key: "lifestyle", icon: "lifestyle" },
];

const buildHeatmap = (evo) => {
  const raw = evo.category_momentum_24h || [];
  const byKey = {};
  for (const r of raw) byKey[`${r.category}|${r.source}`] = r;
  return HEAT_ROWS.map((row) => ({
    cat: row.cat,
    icon: row.icon,
    cells: HEAT_COLS.map((src) => {
      const m = byKey[`${row.key}|${src}`];
      if (!m) return 0;
      // backend snapshot uses current_count; older payloads used items_count
      return Number(m.current_count ?? m.items_count ?? 0) || 0;
    }),
  }));
};

const SRC_FILE_LABEL = {
  discoversnoop: "discover",
  google_news: "gnews",
  reddit: "reddit",
  youtube_trending: "youtube",
  google_trends: "trends",
  wikimedia: "wiki",
  x_trends: "x",
  msn: "msn",
};

const buildPulse = (evo) => {
  const timeline = evo.source_timeline_7d || {};
  const out = [];
  for (const [fileKey, points] of Object.entries(timeline)) {
    const key = SRC_FILE_LABEL[fileKey] || fileKey;
    const counts = points.map((p) => p.count);
    const items = counts[counts.length - 1] || 0;
    const first = counts[0] || 0;
    const delta = items - first;
    const pctNum = first ? Math.round((delta / first) * 100) : items > 0 ? 100 : 0;
    const sign = pctNum >= 0 ? "+" : "";
    let status = "ok";
    if (items === 0) status = "hs";
    else if (delta < 0 && Math.abs(pctNum) > 15) status = "warn";
    out.push({
      key,
      label: fileKey,
      items,
      spark: counts,
      delta7: `${sign}${pctNum}%`,
      status,
    });
  }
  return out;
};

/* ---------- renderers ---------- */

const renderHero = (evo) => {
  const ago = evo?.generated_at ? fmtAgo(evo.generated_at) : "en attente";
  return h(
    "section",
    { class: "tp-hero" },
    h(
      "div",
      { class: "tp-eyebrow" },
      h("span", { class: "dot" }),
      "Évolution ",
      h("span", { class: "muted" }, `· généré ${ago}`),
    ),
    h(
      "h1",
      { class: "tp-title" },
      "Ce qui ",
      h("span", { class: "accent" }, "monte"),
      ", ce qui dure, ce qui s'éteint",
    ),
    h(
      "p",
      { class: "tp-sub" },
      "Historique des 7 derniers jours pour repérer les tendances montantes (candidats anticipation Discover), les sujets persistants, et la santé du pipeline.",
    ),
  );
};

const SecHead = (icon, color, soft, title, desc) =>
  h(
    "div",
    { class: "evo-section evo-block" },
    h(
      "div",
      { class: "evo-h" },
      h(
        "span",
        { class: "ic", style: { background: soft, color } },
        (() => {
          const i = icon();
          i.setAttribute("width", "18");
          i.setAttribute("height", "18");
          return i;
        })(),
      ),
      h("h2", {}, title),
    ),
    h("p", { class: "evo-desc", html: desc }),
  );

const TypeBadge = (type) => {
  const m = TYPE_META[type] || TYPE_META.entity;
  const c = HUE[m.hue];
  return h(
    "span",
    {
      class: "evo-tbadge",
      style: {
        color: c,
        "border-color": `color-mix(in srgb, ${c} 45%, var(--line-2))`,
      },
    },
    m.label,
  );
};

const renderRisingTable = (rows) => {
  if (!rows.length) {
    return h(
      "div",
      { class: "evo-section" },
      h(
        "div",
        {
          class: "evo-dwrap",
          style: { padding: "32px", "text-align": "center", color: "var(--fg-muted)", "font-size": "13px" },
        },
        "Pas encore d'historique. Le premier snapshot DB doit être suivi d'au moins un second pour calculer les variations (toutes les 6h).",
      ),
    );
  }
  const maxArt = Math.max(...rows.map((r) => r.articles), 1);
  const tbody = h("tbody");
  rows.forEach((r, i) => {
    const isNew = r.delta === "new";
    const dir = isNew ? 1 : r.delta >= 0 ? 1 : -1;
    const sparkColor = dir > 0 ? "var(--up)" : "var(--down)";
    tbody.appendChild(
      h(
        "tr",
        {},
        h("td", { class: "evo-dt-rank" }, String(i + 1).padStart(2, "0")),
        h("td", { class: "evo-dt-topic" }, r.topic),
        h("td", {}, TypeBadge(r.type)),
        h(
          "td",
          {},
          h(
            "div",
            { class: "evo-dt-art-wrap" },
            h(
              "div",
              { class: "evo-dt-artbar" },
              h("i", {
                style: { width: (r.articles / maxArt) * 100 + "%" },
              }),
            ),
            h("span", { class: "evo-dt-art" }, String(r.articles)),
          ),
        ),
        h(
          "td",
          { style: { "text-align": "center" } },
          isNew
            ? h("span", { class: "evo-badge-new" }, "NEW")
            : Delta(r.delta),
        ),
        h(
          "td",
          { style: { padding: "6px 18px" } },
          h(
            "div",
            { style: { display: "flex", "justify-content": "center" } },
            Sparkline(r.spark, { w: 104, h: 28, color: sparkColor }),
          ),
        ),
        h(
          "td",
          {
            class: "evo-dt-pct",
            style: {
              color: isNew
                ? "var(--brand)"
                : dir > 0
                  ? "var(--up)"
                  : "var(--down)",
            },
          },
          r.pct,
        ),
      ),
    );
  });
  return h(
    "div",
    { class: "evo-section" },
    h(
      "div",
      { class: "evo-dwrap" },
      h(
        "table",
        { class: "evo-dtable" },
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", {}, "Rang"),
            h("th", {}, "Topic"),
            h("th", {}, "Type"),
            h("th", { class: "num" }, "Articles"),
            h("th", { class: "ctr" }, "Δ 24 h"),
            h("th", { class: "ctr" }, "Tendance"),
            h("th", { class: "num" }, "% var"),
          ),
        ),
        tbody,
      ),
    ),
  );
};

const renderPersistCard = (d) => {
  const statusColor =
    d.status === "up"
      ? "var(--up)"
      : d.status === "flat"
        ? "var(--cool)"
        : "var(--down)";
  const cur = d.score[d.score.length - 1];
  const diff = cur - (d.score[0] || 0);

  const dots = [];
  for (let i = 0; i < d.total; i++) {
    const on = i >= d.total - d.app;
    dots.push(
      h("span", {
        class: "evo-dot-day",
        style: { background: on ? statusColor : "var(--ink-4)" },
      }),
    );
  }
  return h(
    "div",
    { class: "evo-pcard" },
    h(
      "div",
      { class: "evo-pcard-top" },
      h("span", { class: "evo-pcard-name" }, d.topic),
      TypeBadge(d.type),
    ),
    h(
      "div",
      { class: "evo-dots" },
      ...dots,
      h("span", { class: "lbl" }, `${d.app}/${d.total} snapshots`),
    ),
    h(
      "div",
      { class: "evo-pcard-foot" },
      h(
        "span",
        { class: "evo-pcard-score" },
        "signal ",
        h("b", {}, String(cur)),
      ),
      h(
        "div",
        { style: { display: "flex", "align-items": "center", gap: "10px" } },
        Sparkline(d.score, { w: 70, h: 26, color: statusColor, area: false }),
        Delta(diff),
      ),
    ),
  );
};

const renderPersistent = (persistent) => {
  if (!persistent.length) {
    return h(
      "div",
      { class: "evo-section" },
      h(
        "div",
        {
          class: "evo-pcard",
          style: { "text-align": "center", color: "var(--fg-muted)", "font-size": "13px" },
        },
        "Pas encore de sujet ré-apparu. Au moins 2 snapshots du même titre nécessaires pour identifier les persistants.",
      ),
    );
  }
  const grid = h("div", { class: "evo-pgrid" });
  persistent.forEach((d) => grid.appendChild(renderPersistCard(d)));
  return h("div", { class: "evo-section" }, grid);
};

const heatBg = (c, max) => {
  if (c <= 0) return null;
  const t = 0.16 + 0.84 * Math.sqrt(c / max);
  return `color-mix(in srgb, var(--hot) ${Math.round(t * 100)}%, var(--ink-3))`;
};

const renderHeatmap = (rows) => {
  if (!rows.length) return null;
  const allCells = rows.flatMap((r) => r.cells);
  const max = Math.max(1, ...allCells);

  const grid = h("div", { class: "evo-heat" });
  grid.appendChild(h("div", { class: "evo-heat-corner" }));
  HEAT_COLS.forEach((c) => {
    const G = SRC_GLYPH[c];
    grid.appendChild(
      h(
        "div",
        { class: "evo-heat-colh" },
        h(
          "span",
          { class: "g", style: { color: HUE[SRC_HUE[c]] } },
          G ? G() : null,
        ),
        h("span", { class: "lbl" }, c),
      ),
    );
  });

  rows.forEach((row) => {
    const I = CAT_ICON[row.icon];
    grid.appendChild(
      h(
        "div",
        { class: "evo-heat-rowh" },
        h("span", { class: "ic" }, I ? I() : null),
        h("span", { class: "lbl" }, row.cat),
      ),
    );
    row.cells.forEach((c, j) => {
      const bg = heatBg(c, max);
      const t = c <= 0 ? 0 : 0.16 + 0.84 * Math.sqrt(c / max);
      grid.appendChild(
        h(
          "div",
          {
            class: "evo-hcell" + (c <= 0 ? " zero" : ""),
            style: bg ? { background: bg } : {},
            title: `${row.cat} × ${HEAT_COLS[j]} : ${c}`,
          },
          h(
            "span",
            {
              class: "c",
              style: c <= 0 ? {} : { color: t > 0.45 ? "#fff" : "var(--fg)" },
            },
            String(c),
          ),
        ),
      );
    });
  });

  return h(
    "div",
    { class: "evo-section" },
    h("div", { class: "evo-heatwrap" }, grid),
    h(
      "div",
      { class: "evo-heat-legend" },
      h("span", {}, "Faible"),
      h("span", {
        class: "evo-legend-scale",
        style: {
          background:
            "linear-gradient(90deg, var(--ink-3), color-mix(in srgb,var(--hot) 55%,var(--ink-3)), var(--hot))",
        },
      }),
      h(
        "span",
        {},
        "Forte activité 24 h · cellule = nb d'items dans la cat × source",
      ),
    ),
  );
};

const renderPulseCard = (d) => {
  const hue = HUE[SRC_HUE[d.key]] || "var(--brand)";
  const G = SRC_GLYPH[d.key];
  const neg = d.delta7.includes("-") || d.status === "hs" || d.status === "warn";
  const deltaColor =
    d.status === "hs"
      ? "var(--fg-faint)"
      : neg
        ? "var(--down)"
        : "var(--up)";
  const tag =
    d.status === "hs"
      ? { cls: "evo-tag-hs", txt: "Muet" }
      : d.status === "warn"
        ? { cls: "evo-tag-warn", txt: "En baisse" }
        : { cls: "evo-tag-ok", txt: "Actif" };

  return h(
    "div",
    { class: "evo-pulse-card" + (d.status === "hs" ? " hs" : "") },
    h(
      "div",
      { class: "evo-pc-top" },
      h(
        "span",
        {
          class: "evo-pc-name",
          style: {
            color: d.status === "hs" ? "var(--down)" : "var(--fg)",
          },
        },
        h("span", { class: "g", style: { color: hue } }, G ? G() : null),
        d.label,
      ),
      h("span", { class: "evo-pc-items" }, `${d.items} items`),
    ),
    h(
      "div",
      { class: "evo-pc-spark" },
      Sparkline(d.spark, {
        w: 240,
        h: 42,
        color: d.status === "hs" ? "var(--down)" : hue,
      }),
    ),
    h(
      "div",
      { class: "evo-pc-foot" },
      h(
        "span",
        { style: { "white-space": "nowrap" } },
        `${d.spark.length} snapshots · `,
        h(
          "span",
          { class: "evo-pc-delta", style: { color: deltaColor } },
          `Δ7j ${d.delta7}`,
        ),
      ),
      h("span", { class: "evo-pc-tag " + tag.cls }, tag.txt),
    ),
  );
};

const renderPulse = (pulse) => {
  if (!pulse.length) return null;
  const grid = h("div", { class: "evo-pulse-grid" });
  pulse.forEach((d) => grid.appendChild(renderPulseCard(d)));
  return h(
    "div",
    { class: "evo-section", style: { "padding-bottom": "90px" } },
    grid,
  );
};

/* ---------- render principal ---------- */

const render = () => {
  const root = document.getElementById("cp-root");
  if (!root) return;
  root.innerHTML = "";

  const evo = state.evo;
  root.appendChild(renderHero(evo));

  if (state.loading) {
    root.appendChild(
      h(
        "div",
        {
          class: "evo-section",
          style: { padding: "60px 28px", "text-align": "center", color: "var(--fg-muted)" },
        },
        "Chargement…",
      ),
    );
    return;
  }

  if (!evo || !evo.available) {
    root.appendChild(
      h(
        "div",
        {
          class: "evo-section",
          style: { padding: "60px 28px", "text-align": "center", color: "var(--fg-muted)" },
        },
        h(
          "p",
          {},
          evo?.reason
            ? `Évolution indisponible : ${evo.reason}`
            : "Aucun snapshot DB pour l'instant. La page sera peuplée au premier passage du pipeline avec DATABASE_URL.",
        ),
      ),
    );
    return;
  }

  // 1. Rising
  root.appendChild(
    SecHead(
      Ic.trend,
      "var(--up)",
      "var(--up-soft)",
      "Topics qui montent (24 h)",
      "Variation du nombre d'items par entité / cluster / catégorie sur les dernières 24 h. Les <b>nouvelles entrées</b> et les fortes hausses sont des candidats anticipation.",
    ),
  );
  root.appendChild(renderRisingTable(buildRisingRows(evo)));

  // 2. Persistent
  root.appendChild(
    SecHead(
      Ic.radar,
      "var(--warm)",
      "var(--warm-soft)",
      "Sujets persistants (3 derniers jours)",
      "Sujets apparus dans plusieurs snapshots consécutifs. Un sujet avec <b>≥3 apparitions et un score en hausse</b> = signal éditorial durable, vs sujet ponctuel d'un seul cycle.",
    ),
  );
  root.appendChild(renderPersistent(buildPersistent(evo)));

  // 3. Heatmap
  root.appendChild(
    SecHead(
      Ic.flame,
      "var(--hot)",
      "var(--hot-soft)",
      "Catégories qui s'activent (24 h)",
      "Variation du nombre d'items par <b>catégorie × source</b> sur les dernières 24 h. Plus la cellule est rouge, plus la catégorie s'active sur cette source.",
    ),
  );
  const hm = renderHeatmap(buildHeatmap(evo));
  if (hm) root.appendChild(hm);

  // 4. Pulse
  root.appendChild(
    SecHead(
      Ic.pulse,
      "var(--brand)",
      "var(--brand-soft)",
      "Pulse des sources (7 jours)",
      "Évolution du nombre d'items collectés par source à chaque snapshot. Une courbe à plat = source potentiellement muette ; une hausse = volume d'actu qui monte.",
    ),
  );
  const pl = renderPulse(buildPulse(evo));
  if (pl) root.appendChild(pl);
};

/* ---------- mount ---------- */
const mount = async () => {
  render();
  try {
    const r = await fetch("data/analytics/evolution.json", { cache: "no-store" });
    if (r.ok) state.evo = await r.json();
  } catch {
    // ignore
  }
  state.loading = false;
  render();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
