/* ============================================================
   EDITORIAL SIGNAL — Cockpit Pro (vanilla JS port du design React)
   Implémente le design Claude Design en branchant sur les vraies
   données : data/sujets/latest.json + data/analytics/evolution.json
   ============================================================ */

import { loadSujets, formatLongDate, formatFreshness } from "./api.js?v=tbr5";

/* ---------- helpers DOM (h-tagged function, comme React.createElement) ---------- */
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

/* ---------- Editorial Signal logo (piste A : barres + balise) ---------- */
const BRAND_MARK_SVG = `<svg viewBox="0 0 48 48" fill="none" width="30" height="30" aria-label="Editorial Signal">
  <rect x="5"  y="30" width="7" height="12" rx="2.4" fill="#5A6275"/>
  <rect x="16" y="23" width="7" height="19" rx="2.4" fill="#F5B14B"/>
  <rect x="27" y="15" width="7" height="27" rx="2.4" fill="#FF8A5B"/>
  <rect x="38" y="11" width="7" height="31" rx="2.4" fill="#FF6A4D"/>
  <circle cx="41.5" cy="5.5" r="5"   fill="rgba(255,106,77,0.22)"/>
  <circle cx="41.5" cy="5.5" r="2.7" fill="#FF6A4D" class="brand-beacon"/>
</svg>`;

const svg = (paths, viewBox = "0 0 24 24", w = 14, h_ = 14) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", viewBox);
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "2");
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("width", String(w));
  s.setAttribute("height", String(h_));
  s.innerHTML = paths;
  return s;
};

const Ic = {
  search: () => svg('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>'),
  arrow: () => svg('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  chevron: () => svg('<path d="m6 9 6 6 6-6"/>'),
  up: (s) => svg('<path d="m6 15 6-6 6 6"/>', "0 0 24 24", s || 11, s || 11),
  down: (s) => svg('<path d="m6 9 6 6 6-6"/>', "0 0 24 24", s || 11, s || 11),
  flat: (s) => svg('<path d="M5 12h14"/>', "0 0 24 24", s || 11, s || 11),
  trend: (s) => svg('<path d="m3 17 6-6 4 4 8-8"/><path d="M17 7h4v4"/>', "0 0 24 24", s || 15, s || 15),
  layers: (s) =>
    svg(
      '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
      "0 0 24 24",
      s || 15,
      s || 15,
    ),
  cluster: (s) =>
    svg(
      '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="17" r="2.5"/><path d="M8 7.5 10.5 15M16 9l-3 5.5"/>',
      "0 0 24 24",
      s || 15,
      s || 15,
    ),
  tag: (s) => svg('<path d="M3 7v5l8 8 8-8-8-8H7a4 4 0 0 0-4 3Z"/><circle cx="8" cy="9" r="1"/>', "0 0 24 24", s || 15, s || 15),
  flame: (s) => svg('<path d="M12 3c1 3 4 4 4 8a4 4 0 0 1-8 0c0-1 .5-2 1-2.5C9 11 12 9 12 3Z"/>', "0 0 24 24", s || 14, s || 14),
  pulse: (s) => svg('<path d="M3 12h4l2-6 4 12 2-6h6"/>', "0 0 24 24", s || 14, s || 14),
  x: (s) => svg('<path d="M6 6l12 12M18 6 6 18"/>', "0 0 24 24", s || 16, s || 16),
  user: (s) => svg('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>', "0 0 24 24", s || 16, s || 16),
  bookmark: (s) => svg('<path d="M6 4h12v16l-6-4-6 4V4Z"/>', "0 0 24 24", s || 16, s || 16),
  eye: (s) => svg('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/>', "0 0 24 24", s || 15, s || 15),
};

const SRC_GLYPH = {
  discover: () =>
    svg(
      '<circle cx="12" cy="12" r="8"/><path d="m9 15 1.5-4.5L15 9l-1.5 4.5L9 15Z" fill="currentColor" stroke="none"/>',
      "0 0 24 24",
      12,
      12,
    ),
  gnews: () => svg('<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 12h8M8 15h5"/>', "0 0 24 24", 12, 12),
  trends: () => svg('<path d="m4 16 5-5 3 3 7-7"/><path d="M16 7h4v4"/>', "0 0 24 24", 12, 12),
  wiki: () => svg('<path d="M3 7 7 17 10.5 9 14 17 21 7"/>', "0 0 24 24", 12, 12),
  msn: () => svg('<path d="M4 18V7l4 6 4-6 4 6 4-6v11"/>', "0 0 24 24", 12, 12),
  x: () => svg('<path d="M5 5l14 14M19 5 5 19"/>', "0 0 24 24", 12, 12),
  reddit: () =>
    svg(
      '<circle cx="12" cy="13" r="7"/><circle cx="12" cy="4" r="1.4"/><path d="M12 5.5V9"/><circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none"/><path d="M9.5 16c1.5 1 3.5 1 5 0"/>',
      "0 0 24 24",
      12,
      12,
    ),
  youtube: () =>
    svg('<rect x="3" y="6" width="18" height="12" rx="3"/><path d="m10 9 6 3-6 3V9Z" fill="currentColor" stroke="none"/>', "0 0 24 24", 12, 12),
};

/* ---------- domaine : mapping catégories, sources, scoring ---------- */

const HUE = {
  indigo: "#818CF8",
  pink: "#F472B6",
  emerald: "#34D399",
  purple: "#C084FC",
  amber: "#FBBF24",
  blue: "#60A5FA",
  red: "#FB7185",
};

// 6 buckets de catégorie inspirés du design
const CATEGORIES = {
  ACTUALITE: { label: "Actualité", hue: "indigo" },
  DIVERTISSEMENT: { label: "Divertissement", hue: "pink" },
  SPORT: { label: "Sport", hue: "emerald" },
  VIDEO: { label: "Vidéo", hue: "purple" },
  FINANCE: { label: "Finance", hue: "amber" },
  LIFESTYLE: { label: "Lifestyle", hue: "blue" },
};

// Mappe une discover_category Google taxonomy → 1 des 6 buckets canoniques
const mapDiscoverToCat = (cat) => {
  if (!cat) return "ACTUALITE";
  const c = cat.toLowerCase();
  if (c.includes("sport")) return "SPORT";
  if (c.includes("arts") || c.includes("entertainment") || c.includes("people") || c.includes("celebrit"))
    return "DIVERTISSEMENT";
  if (c.includes("video")) return "VIDEO";
  if (c.includes("finance") || c.includes("business") || c.includes("econom")) return "FINANCE";
  if (c.includes("food") || c.includes("travel") || c.includes("home") || c.includes("auto") || c.includes("pet") || c.includes("hobby") || c.includes("beauty"))
    return "LIFESTYLE";
  return "ACTUALITE";
};

const SOURCES = {
  discover: { label: "Google Discover", short: "GD" },
  gnews: { label: "Google News", short: "GN" },
  trends: { label: "Google Trends", short: "GT" },
  wiki: { label: "Wikipédia", short: "W" },
  msn: { label: "MSN", short: "M" },
  x: { label: "X / Twitter", short: "X" },
  reddit: { label: "Reddit", short: "R" },
  youtube: { label: "YouTube", short: "YT" },
};

// Seuils sur l'echelle d'affichage (= 50/30 internal x1.2).
const tierOf = (score) => {
  if (score >= 60) return { key: "fort", label: "Signal fort", color: "var(--hot)", spine: "var(--hot)", glow: "rgba(255,106,77,0.16)" };
  if (score >= 36) return { key: "moyen", label: "Signal moyen", color: "var(--warm)", spine: "var(--warm)", glow: "rgba(245,177,75,0.13)" };
  return { key: "faible", label: "Signal faible", color: "var(--cool)", spine: "var(--cool)", glow: "rgba(126,138,163,0.10)" };
};

const fmtDelta = (d) => (d > 0 ? "+" : "") + d;

/* ---------- transformation data backend → shape design ---------- */

/** Convertit un sujet du payload en shape attendue par les renderers. */
const adaptSujet = (raw) => {
  const sigs = raw.signals || [];
  // Filtre les pills MSN (présence) hors top affichage si on a déjà autre chose
  const sources = sigs
    .filter((s) => s.label !== "msn" || sigs.length === 1)
    .map((s) => {
      // s.label = discover|gnews|reddit|youtube|trends|wiki|x|msn
      const key = s.label;
      return { key, v: s.value };
    });
  return {
    rank: raw.rank,
    score: raw.score,
    title: raw.title,
    cat: mapDiscoverToCat(raw.discover_category),
    delta: 0, // injecté plus tard depuis evolution.json si possible
    articles: (raw.refs || []).length || sources.length,
    sources,
    entities: raw.discover_entities || [],
    snippet: raw.rationale || "",
    msn_url: raw.msn_url,
    refs: raw.refs || [],
  };
};

/** Charge evolution.json (analytics) si dispo. Non bloquant. */
const tryLoadEvolution = async () => {
  try {
    const r = await fetch("data/analytics/evolution.json", { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
};

/* ---------- état global ---------- */

const state = {
  raw: null, // payload sujets
  evo: null, // payload analytics
  topics: [], // sujets adaptés
  query: "",
  sort: "score",
  catFilter: null,
  railFilter: null,
  openRank: null,
  drawer: null,
};

const setState = (patch) => {
  Object.assign(state, patch);
  render();
};

/* ---------- petits composants ---------- */

const Delta = (d, showZero = true) => {
  if (d === 0)
    return showZero ? h("span", { class: "delta flat" }, Ic.flat(11), "0") : null;
  const up = d > 0;
  return h("span", { class: "delta " + (up ? "up" : "down") }, up ? Ic.up(11) : Ic.down(11), fmtDelta(d));
};

const Gauge = (score, size = 58, stroke = 5, showLabel = true) => {
  const t = tierOf(score);
  const numSize = size >= 56 ? 18 : size >= 44 ? 15 : 13;
  const ring = h("div", {
    style: {
      width: size + "px",
      height: size + "px",
      borderRadius: "50%",
      background: `conic-gradient(${t.color} ${score * 3.6}deg, var(--ink-4) 0deg)`,
      WebkitMask: `radial-gradient(closest-side, transparent calc(100% - ${stroke}px), #000 calc(100% - ${stroke}px))`,
      mask: `radial-gradient(closest-side, transparent calc(100% - ${stroke}px), #000 calc(100% - ${stroke}px))`,
    },
  });
  const num = h(
    "span",
    {
      class: "num",
      style: { "font-size": numSize + "px", color: t.color, top: showLabel ? "30%" : "50%", transform: "translateY(-50%)" },
    },
    String(score),
  );
  const lab = showLabel ? h("span", { class: "lab", style: { bottom: "24%" } }, "signal") : null;
  return h("div", { class: "gauge", style: { width: size + "px", height: size + "px" } }, ring, num, lab);
};

const TierChip = (score) => {
  const t = tierOf(score);
  return h("span", { class: "tier " + t.key }, h("span", { class: "tier-dot" }), t.label);
};

const CatChip = (catKey) => {
  const c = CATEGORIES[catKey] || { label: catKey, hue: "indigo" };
  return h(
    "span",
    { class: "cat-chip" },
    h("span", { class: "cat-dot", style: { "--cat": HUE[c.hue], background: HUE[c.hue] } }),
    c.label,
  );
};

const SourceRow = (sources, max = 4) => {
  const shown = sources.slice(0, max);
  const extra = sources.length - shown.length;
  const wrap = h("div", { class: "sources" });
  for (const s of shown) {
    const meta = SOURCES[s.key];
    const G = SRC_GLYPH[s.key];
    const span = h(
      "span",
      { class: "src", title: `${meta?.label || s.key} · ${s.v}` },
      G ? G() : h("span", { style: { "font-size": "9px", "font-weight": "700" } }, meta?.short || "?"),
    );
    wrap.appendChild(span);
  }
  if (extra > 0) wrap.appendChild(h("span", { class: "src-more" }, "+" + extra));
  return wrap;
};

/* ---------- TopNav ---------- */

const renderTopNav = () => {
  const links = [
    { label: "Flux global", href: "index.html", active: true },
    { label: "Sources", href: "tendances.html" },
    { label: "Catégories", href: "categories.html" },
    { label: "Évolution", href: "evolution.html" },
    { label: "Projets", href: "projects.html" },
  ];
  return h(
    "nav",
    { class: "topnav" },
    h(
      "div",
      { class: "topnav-inner" },
      h(
        "div",
        { class: "cp-brand" },
        h("div", { class: "brand-mark", html: BRAND_MARK_SVG }),
        h(
          "div",
          { class: "brand-text" },
          h(
            "span",
            { class: "brand-name" },
            "EDITORIAL ",
            h("span", { class: "brand-name__accent" }, "SIGNAL"),
          ),
          h(
            "span",
            { class: "brand-sub" },
            h("span", { class: "brand-sub__dot" }),
            "The Black Room",
          ),
        ),
      ),
      h(
        "div",
        { class: "nav-links" },
        ...links.map((l) =>
          h("a", { class: "nav-link" + (l.active ? " active" : ""), href: l.href }, l.label),
        ),
      ),
      h("div", { class: "nav-spacer" }),
      h(
        "div",
        { class: "nav-search" },
        Ic.search(),
        h("input", {
          value: state.query,
          placeholder: "Rechercher un sujet, une entité…",
          oninput: (e) => setState({ query: e.target.value, openRank: null }),
        }),
        !state.query ? h("kbd", {}, "/") : null,
      ),
      h(
        "div",
        { class: "user-chip" },
        h(
          "div",
          { class: "user-meta" },
          h("div", { class: "user-role" }, "Rédac chef"),
          h("div", { class: "user-name" }, "Clément P."),
        ),
        h(
          "button",
          {
            class: "cp-avatar",
            "data-auth-logout": "",
            title: "Cliquer pour se déconnecter",
          },
          "CP",
        ),
      ),
    ),
  );
};

/* ---------- TodayBar ---------- */

const renderTodayBar = () => {
  const generated = state.raw?.generated_at;
  const dateStr = generated ? (() => {
    const long = formatLongDate(generated);
    return long ? long.charAt(0).toUpperCase() + long.slice(1) : "";
  })() : "—";
  const fresh = generated ? formatFreshness(generated) : "Pipeline en attente…";
  const sourcesUsed = state.raw?.sources_used || {};
  const nSources = Object.keys(sourcesUsed).length;
  const nActive = Object.values(sourcesUsed).filter((s) => (s?.count ?? 0) > 0).length;
  const nSujets = state.topics.length;

  return h(
    "div",
    { class: "todaybar" },
    h(
      "div",
      { class: "todaybar-inner" },
      h("span", { class: "tb-date" }, dateStr),
      h("span", { class: "tb-sep" }),
      h("span", { class: "tb-pill" }, h("span", { class: "live-dot" }), "Pipeline actif"),
      h("span", { class: "tb-sep" }),
      h("span", { class: "tb-pill mono" }, fresh),
      h("span", { class: "tb-sep" }),
      h(
        "span",
        { class: "tb-pill" },
        `${nActive}/${nSources} sources · ${nSujets} sujets analysés`,
      ),
      h(
        "a",
        { class: "tb-cta", href: "evolution.html" },
        "Évolution 7 jours ",
        Ic.arrow(),
      ),
    ),
  );
};

/* ---------- KPI row ---------- */

const Spark = (vals, color) => {
  const mx = Math.max(1, ...vals);
  const wrap = h("div", { class: "spark" });
  for (const v of vals) {
    wrap.appendChild(
      h("i", {
        style: { height: (v / mx) * 100 + "%", background: color, opacity: 0.4 + 0.6 * (v / mx) },
      }),
    );
  }
  return wrap;
};

const renderKpiRow = () => {
  const hot = state.topics.filter((t) => t.score >= 60).length;
  const total = state.topics.length;
  const sourcesUsed = state.raw?.sources_used || {};
  const nSources = Object.keys(sourcesUsed).length;
  const nActive = Object.values(sourcesUsed).filter((s) => (s?.count ?? 0) > 0).length;
  const rising = state.evo?.available
    ? (state.evo.topics_24h || []).filter((t) => t.delta > 0 || t.prev_count === 0).length
    : 0;

  // Spark synthétique pour rising — utilise les counts par snapshot si dispo
  const risingSpark = (() => {
    const tl = state.evo?.source_timeline_7d?.discoversnoop;
    if (!tl || tl.length < 2) return [3, 5, 4, 8, 7, 11, 14, 18, 23];
    return tl.slice(-9).map((p) => p.count);
  })();
  const sourcesSpark = (() => {
    const out = [];
    const tl = state.evo?.source_timeline_7d;
    if (!tl) return [7, 8, 8, 7, 8, 7, 7, 7];
    const len = Math.max(...Object.values(tl).map((v) => v.length));
    for (let i = Math.max(0, len - 8); i < len; i++) {
      let n = 0;
      for (const points of Object.values(tl)) {
        const p = points[i];
        if (p && p.count > 0) n++;
      }
      out.push(n);
    }
    return out.length ? out : [7, 8, 8, 7, 8, 7, 7, 7];
  })();

  const cards = [
    {
      label: "Sujets hot",
      val: hot,
      sub: "score ≥ 60",
      accent: "var(--hot)",
      right: Delta(hot >= 4 ? +2 : 0, false),
    },
    {
      label: "En hausse / 24 h",
      val: rising,
      sub: "sujets avec delta positif",
      accent: "var(--up)",
      right: Spark(risingSpark, "var(--up)"),
    },
    {
      label: "Sources actives",
      val: `${nActive}/${nSources || 7}`,
      sub: `sur ${nSources || 7} surveillées`,
      accent: "var(--brand)",
      right: Spark(sourcesSpark, "var(--brand)"),
    },
    {
      label: "Sujets du jour",
      val: total,
      sub: "dans le ranking du jour",
      accent: "var(--cool)",
      right: Delta(0, false),
    },
  ];

  return h(
    "div",
    { class: "kpi-row" },
    ...cards.map((c, i) =>
      h(
        "div",
        { class: "kpi fade-up", style: { "animation-delay": i * 50 + "ms" } },
        h("span", { class: "kpi-accent", style: { background: c.accent } }),
        h("div", { class: "kpi-top" }, h("span", { class: "kpi-label" }, c.label), c.right),
        h("div", { class: "kpi-val" }, String(c.val)),
        h("div", { class: "kpi-sub" }, c.sub),
      ),
    ),
  );
};

/* ---------- Hero cards ---------- */

const renderHero = () => {
  const top3 = state.topics.slice(0, 3);
  return h(
    "div",
    {},
    h(
      "div",
      { class: "sec-head" },
      h("span", { class: "sec-title" }, "À la une"),
      h("span", { class: "sec-sub" }, "les 3 sujets au plus fort signal — clic pour le détail"),
    ),
    h(
      "div",
      { class: "hero-grid" },
      ...top3.map((t, i) => {
        const tier = tierOf(t.score);
        return h(
          "div",
          {
            class: "hero fade-up",
            style: { "--glow": tier.glow, "animation-delay": i * 60 + "ms" },
            onClick: () => setState({ drawer: t }),
          },
          h(
            "div",
            { class: "hero-top" },
            h(
              "div",
              {},
              h("div", { class: "hero-rank" }, `À LA UNE · ${String(t.rank).padStart(2, "0")}`),
              h("div", { style: { "margin-top": "10px" } }, TierChip(t.score)),
            ),
            Gauge(t.score, 62, 5),
          ),
          h("div", { class: "hero-title" }, t.title),
          h(
            "div",
            { class: "hero-foot" },
            CatChip(t.cat),
            h(
              "div",
              { style: { display: "flex", "align-items": "center", gap: "10px" } },
              SourceRow(t.sources, 3),
              Delta(t.delta, false),
            ),
          ),
        );
      }),
    ),
  );
};

/* ---------- Toolbar (sort + cat filter) ---------- */

const renderToolbar = () => {
  const sorts = [
    { key: "score", label: "Signal", icon: Ic.flame() },
    { key: "rising", label: "En hausse", icon: Ic.trend() },
    { key: "recent", label: "Récents", icon: Ic.pulse() },
  ];
  const segBtns = sorts.map((s) =>
    h(
      "button",
      { class: state.sort === s.key ? "on" : "", onClick: () => setState({ sort: s.key }) },
      s.icon,
      s.label,
    ),
  );
  const cats = Object.keys(CATEGORIES);
  const chips = [
    h(
      "button",
      {
        class: "chip" + (state.catFilter === null ? " on" : ""),
        onClick: () => setState({ catFilter: null }),
      },
      "Toutes",
    ),
    ...cats.map((c) =>
      h(
        "button",
        {
          class: "chip" + (state.catFilter === c ? " on" : ""),
          onClick: () => setState({ catFilter: state.catFilter === c ? null : c }),
        },
        h("span", { class: "cat-dot", style: { background: HUE[CATEGORIES[c].hue] } }),
        CATEGORIES[c].label,
      ),
    ),
  ];

  return h(
    "div",
    { class: "toolbar" },
    h("div", { class: "seg" }, ...segBtns),
    h("div", { style: { width: "1px", height: "22px", background: "var(--line-2)", margin: "0 2px" } }),
    ...chips,
  );
};

/* ---------- List rows ---------- */

const renderRow = (t) => {
  const tier = tierOf(t.score);
  const open = state.openRank === t.rank;
  const row = h(
    "div",
    {
      class: "row" + (open ? " open" : ""),
      style: { "--spine": tier.spine },
      onClick: () => setState({ openRank: open ? null : t.rank }),
    },
    h("div", { class: "row-rank" }, String(t.rank).padStart(2, "0")),
    h("div", { class: "row-score", style: { color: tier.color } }, String(t.score)),
    h(
      "div",
      { class: "row-mid" },
      h("div", { class: "row-title" }, t.title),
      h(
        "div",
        { class: "row-meta" },
        CatChip(t.cat),
        h("div", { class: "bar" }, h("i", { style: { width: t.score + "%", background: tier.color } })),
      ),
    ),
    h(
      "div",
      { class: "row-right" },
      SourceRow(t.sources, 4),
      Delta(t.delta, false),
      (() => {
        const c = Ic.chevron();
        c.classList.add("row-chev");
        c.setAttribute("width", "18");
        c.setAttribute("height", "18");
        return c;
      })(),
    ),
  );

  const wrap = h("div", {});
  wrap.appendChild(row);

  if (open) {
    wrap.appendChild(renderDetail(t));
  }
  return wrap;
};

const renderDetail = (t) => {
  const left = h(
    "div",
    {},
    h("h6", {}, "Pourquoi ce sujet"),
    h("p", { class: "snip" }, t.snippet),
    h("h6", {}, "Entités liées"),
    h(
      "div",
      { class: "ent-tags" },
      ...t.entities.map((e) => h("span", { class: "ent" }, e)),
    ),
    h(
      "div",
      { class: "actions" },
      h(
        "button",
        {
          class: "cp-btn cp-btn-primary",
          onClick: (e) => {
            e.stopPropagation();
            setState({ drawer: t });
          },
        },
        Ic.eye(15),
        "Voir le détail complet",
      ),
      h("button", { class: "cp-btn cp-btn-ghost", onClick: (e) => e.stopPropagation() }, Ic.user(15), "Assigner"),
    ),
  );
  const right = h(
    "div",
    {},
    h("h6", {}, "Répartition des signaux"),
    ...t.sources.map((s) => {
      const meta = SOURCES[s.key] || { label: s.key };
      const G = SRC_GLYPH[s.key];
      return h(
        "div",
        { class: "src-line" },
        h(
          "div",
          { class: "src-line-l" },
          h("span", { class: "src", style: { width: "24px", height: "24px" } }, G ? G() : null),
          h("span", { class: "src-line-name" }, meta.label),
        ),
        h("span", { class: "src-line-v" }, s.v),
      );
    }),
  );
  return h(
    "div",
    { class: "detail", onClick: (e) => e.stopPropagation() },
    h("div", { class: "detail-grid" }, left, right),
  );
};

const renderList = (visible) => {
  // grouped si tri par score + sans filtre
  const grouped = state.sort === "score" && !state.catFilter && !state.query && !state.railFilter;
  if (!grouped) {
    if (visible.length === 0) {
      return h(
        "div",
        {
          style: {
            padding: "40px 20px",
            "text-align": "center",
            color: "var(--fg-subtle)",
            border: "1px dashed var(--line-2)",
            "border-radius": "var(--r-lg)",
          },
        },
        "Aucun sujet ne correspond. ",
        h("button", { class: "clearfilter", onClick: () => setState({ catFilter: null, query: "", railFilter: null }) }, "Réinitialiser"),
      );
    }
    const wrap = h("div", { class: "list" });
    visible.forEach((t) => wrap.appendChild(renderRow(t)));
    return wrap;
  }

  const tiers = [
    { key: "fort", label: "Signal fort", items: visible.filter((t) => t.score >= 60) },
    { key: "moyen", label: "Signal moyen", items: visible.filter((t) => t.score >= 36 && t.score < 60) },
    { key: "faible", label: "Signal faible", items: visible.filter((t) => t.score < 30) },
  ];
  const wrap = h("div", { class: "list" });
  for (const g of tiers) {
    if (g.items.length === 0) continue;
    wrap.appendChild(
      h(
        "div",
        { class: "tier-divider" },
        h("span", { class: "tier " + g.key }, h("span", { class: "tier-dot" }), g.label),
        h("span", { class: "line" }),
        h("span", { class: "mono", style: { "font-size": "11px", color: "var(--fg-subtle)" } }, g.items.length + " sujets"),
      ),
    );
    g.items.forEach((t) => wrap.appendChild(renderRow(t)));
  }
  return wrap;
};

/* ---------- Rail panels ---------- */

const PanelHead = (icon, color, soft, title, sub) =>
  h(
    "div",
    { class: "panel-head" },
    h("span", { class: "panel-icon", style: { background: soft, color } }, icon),
    h(
      "div",
      {},
      h("div", { class: "panel-title" }, title),
      sub ? h("div", { class: "panel-sub" }, sub) : null,
    ),
  );

const renderRisingPanel = () => {
  // Source de vérité : evolution.json (topics_24h delta > 0). Fallback : sujets actuels.
  const evoRising = (state.evo?.topics_24h || []).filter((t) => t.delta > 0 || t.prev_count === 0).slice(0, 5);
  const body = h("div", { class: "panel-body" });

  if (evoRising.length > 0) {
    evoRising.forEach((t, i) => {
      const isNew = t.prev_count === 0;
      body.appendChild(
        h(
          "div",
          { class: "rise" },
          h("span", { class: "rise-rank" }, String(i + 1)),
          h(
            "div",
            { class: "rise-body" },
            h("div", { class: "rise-name" }, t.topic_label || t.topic_name),
            h(
              "div",
              { class: "rise-meta" },
              `${t.topic_kind === "entity" ? "Entité" : t.topic_kind === "cluster" ? "Cluster" : "Catégorie"} · ${t.current_count} articles`,
            ),
          ),
          isNew
            ? h("span", { class: "delta up" }, "NEW")
            : Delta(t.delta),
        ),
      );
    });
  } else if (state.topics.length) {
    // Fallback : top 5 sujets par score
    state.topics
      .slice()
      .sort((a, b) => b.score - a.score)
      .slice(0, 5)
      .forEach((t, i) => {
        body.appendChild(
          h(
            "div",
            { class: "rise", onClick: () => setState({ drawer: t }) },
            h("span", { class: "rise-rank" }, String(i + 1)),
            h(
              "div",
              { class: "rise-body" },
              h("div", { class: "rise-name" }, t.title),
              h(
                "div",
                { class: "rise-meta" },
                `${CATEGORIES[t.cat]?.label || t.cat} · signal ${t.score}`,
              ),
            ),
            Delta(0, true),
          ),
        );
      });
  } else {
    body.appendChild(
      h(
        "div",
        { style: { padding: "20px", color: "var(--fg-subtle)", "font-size": "12px" } },
        "Pas encore d'historique. Premier snapshot DB en attente.",
      ),
    );
  }

  return h(
    "div",
    { class: "panel" },
    PanelHead(Ic.trend(), "var(--up)", "var(--up-soft)", "Topics qui montent", "plus forte progression · 24 h"),
    body,
  );
};

const renderPerfPanel = () => {
  const cats = (state.raw?.categories_trending || []).slice(0, 8);
  if (!cats.length) return null;
  const mx = Math.max(1, ...cats.map((c) => c.total_score || 0));
  const HUES = ["red", "indigo", "pink", "emerald", "blue", "purple", "amber", "blue"];
  const body = h("div", { class: "panel-body" });
  cats.forEach((c, i) => {
    const hue = HUES[i % HUES.length];
    body.appendChild(
      h(
        "div",
        {
          class: "perf",
          onClick: () => setState({ railFilter: c.label, sort: "score", openRank: null }),
        },
        h(
          "div",
          { class: "perf-top" },
          h("span", { class: "perf-name" }, c.label),
          h(
            "div",
            { class: "perf-stat" },
            h("span", { class: "perf-total" }, String(Math.round(c.total_score || 0))),
          ),
        ),
        h("div", { class: "perf-bar" }, h("i", { style: { width: ((c.total_score || 0) / mx) * 100 + "%", background: HUE[hue] } })),
        h(
          "div",
          { class: "perf-foot" },
          h("small", {}, `${c.articles_count || 0} articles`),
          h("small", {}, `moy. ${(c.avg_score || 0).toFixed(1)}`),
        ),
      ),
    );
  });
  return h(
    "div",
    { class: "panel" },
    PanelHead(Ic.layers(), "var(--brand)", "var(--brand-soft)", "Catégories qui performent", "score total · clique pour filtrer"),
    body,
  );
};

const renderUniversePanel = () => {
  const clusters = (state.raw?.entity_clusters || []).slice(0, 5);
  if (!clusters.length) return null;
  const body = h("div", { class: "panel-body" });
  clusters.forEach((u) => {
    body.appendChild(
      h(
        "div",
        { class: "uni", onClick: () => setState({ railFilter: u.label, sort: "score", openRank: null }) },
        h(
          "div",
          { class: "uni-top" },
          h("span", { class: "uni-name" }, u.label),
          h("span", { class: "uni-score" }, String(Math.round(u.total_score || 0))),
        ),
        h(
          "div",
          { class: "uni-tags" },
          ...(u.members || []).slice(0, 4).map((m) => h("span", { class: "uni-tag" }, m)),
        ),
        h(
          "div",
          { class: "uni-foot" },
          `${u.articles_count || 0} articles · ${(u.members || []).length} entités`,
        ),
      ),
    );
  });
  return h(
    "div",
    { class: "panel" },
    PanelHead(Ic.cluster(), "var(--h-purple)", "rgba(192,132,252,0.13)", "Univers à creuser", "entités liées · clique pour filtrer"),
    body,
  );
};

const renderIndivPanel = () => {
  const ents = (state.raw?.entities_trending || []).slice(0, 7);
  if (!ents.length) return null;
  const mx = Math.max(1, ...ents.map((e) => e.total_score || 0));
  const body = h(
    "div",
    { class: "panel-body" },
    h(
      "div",
      { class: "indiv-wrap" },
      ...ents.map((d) =>
        h(
          "div",
          { class: "indiv", onClick: () => setState({ railFilter: d.name, sort: "score", openRank: null }) },
          h("span", {
            class: "indiv-bar",
            style: { background: `hsl(${250 - ((d.total_score || 0) / mx) * 40} 70% 65%)` },
          }),
          h("span", { class: "indiv-name" }, d.name),
          h("span", { class: "indiv-art" }, `${d.articles_count || 0} art.`),
          h("span", { class: "indiv-score" }, String(Math.round(d.total_score || 0))),
        ),
      ),
    ),
  );
  return h(
    "div",
    { class: "panel" },
    PanelHead(Ic.tag(), "var(--h-amber)", "rgba(251,191,36,0.13)", "Topics individuels", "entités isolées · clique pour filtrer"),
    body,
  );
};

const renderRail = () => {
  const rail = h("div", { class: "rail" });
  rail.appendChild(renderRisingPanel());
  const p = renderPerfPanel();
  if (p) rail.appendChild(p);
  const u = renderUniversePanel();
  if (u) rail.appendChild(u);
  const i = renderIndivPanel();
  if (i) rail.appendChild(i);
  return rail;
};

/* ---------- Drawer ---------- */

const renderDrawer = (t) => {
  const tier = tierOf(t.score);
  const onClose = () => setState({ drawer: null });
  const sourcesNode = h("div", {});
  t.sources.forEach((s) => {
    const meta = SOURCES[s.key] || { label: s.key };
    const G = SRC_GLYPH[s.key];
    sourcesNode.appendChild(
      h(
        "div",
        { class: "src-line" },
        h(
          "div",
          { class: "src-line-l" },
          h("span", { class: "src", style: { width: "26px", height: "26px" } }, G ? G() : null),
          h("span", { class: "src-line-name" }, meta.label),
        ),
        h("span", { class: "src-line-v" }, s.v),
      ),
    );
  });
  const refsNode =
    t.refs && t.refs.length
      ? h(
          "div",
          { class: "dr-section" },
          h(
            "h6",
            {
              style: {
                "font-size": "10px",
                "letter-spacing": "0.14em",
                "text-transform": "uppercase",
                color: "var(--fg-subtle)",
                "font-weight": "700",
                "margin-bottom": "10px",
              },
            },
            "Articles de référence",
          ),
          ...t.refs.slice(0, 6).map((r) => {
            const isObj = r && typeof r === "object";
            const label = isObj ? r.label : r;
            const url = isObj ? r.url : t.msn_url;
            return h(
              "div",
              { class: "src-line" },
              h(
                "div",
                { class: "src-line-l" },
                url
                  ? h(
                      "a",
                      {
                        href: url,
                        target: "_blank",
                        rel: "noopener noreferrer",
                        class: "src-line-name",
                        style: { color: "var(--fg)", "text-decoration": "none" },
                      },
                      label,
                    )
                  : h("span", { class: "src-line-name" }, label),
              ),
            );
          }),
        )
      : null;

  return h(
    "div",
    {},
    h("div", { class: "scrim", onClick: onClose }),
    h(
      "aside",
      { class: "drawer" },
      h(
        "div",
        { class: "dr-head" },
        h("button", { class: "dr-close", onClick: onClose }, Ic.x(16)),
        h(
          "div",
          { style: { display: "flex", "align-items": "center", gap: "10px" } },
          TierChip(t.score),
          h(
            "span",
            { class: "mono", style: { "font-size": "12px", color: "var(--fg-subtle)" } },
            `RANG ${String(t.rank).padStart(2, "0")} / ${state.topics.length}`,
          ),
        ),
        h("h2", { class: "dr-title" }, t.title),
        h(
          "div",
          { style: { display: "flex", "align-items": "center", gap: "14px", "margin-top": "10px" } },
          CatChip(t.cat),
          Delta(t.delta),
        ),
      ),
      h(
        "div",
        { class: "dr-body" },
        h(
          "div",
          { class: "metric-grid" },
          h(
            "div",
            { class: "metric" },
            h("div", { class: "metric-v", style: { color: tier.color } }, String(t.score)),
            h("div", { class: "metric-l" }, "Signal score"),
          ),
          h(
            "div",
            { class: "metric" },
            h("div", { class: "metric-v" }, String(t.articles || (t.refs || []).length)),
            h("div", { class: "metric-l" }, "Articles FR"),
          ),
          h(
            "div",
            { class: "metric" },
            h(
              "div",
              { class: "metric-v", style: { color: t.delta >= 0 ? "var(--up)" : "var(--down)" } },
              fmtDelta(t.delta),
            ),
            h("div", { class: "metric-l" }, "Delta 24 h"),
          ),
        ),
        t.snippet
          ? h(
              "div",
              { class: "dr-section" },
              h(
                "h6",
                {
                  style: {
                    "font-size": "10px",
                    "letter-spacing": "0.14em",
                    "text-transform": "uppercase",
                    color: "var(--fg-subtle)",
                    "font-weight": "700",
                    "margin-bottom": "10px",
                  },
                },
                "Lecture éditoriale",
              ),
              h(
                "p",
                {
                  class: "snip",
                  style: { "font-size": "14px", color: "var(--fg-muted)", "line-height": "1.6" },
                },
                t.snippet,
              ),
            )
          : null,
        h(
          "div",
          { class: "dr-section" },
          h(
            "h6",
            {
              style: {
                "font-size": "10px",
                "letter-spacing": "0.14em",
                "text-transform": "uppercase",
                color: "var(--fg-subtle)",
                "font-weight": "700",
                "margin-bottom": "10px",
              },
            },
            "Signaux par source",
          ),
          sourcesNode,
        ),
        t.entities && t.entities.length
          ? h(
              "div",
              { class: "dr-section" },
              h(
                "h6",
                {
                  style: {
                    "font-size": "10px",
                    "letter-spacing": "0.14em",
                    "text-transform": "uppercase",
                    color: "var(--fg-subtle)",
                    "font-weight": "700",
                    "margin-bottom": "10px",
                  },
                },
                "Entités liées",
              ),
              h(
                "div",
                { class: "ent-tags" },
                ...t.entities.map((e) => h("span", { class: "ent" }, e)),
              ),
            )
          : null,
        refsNode,
      ),
      h(
        "div",
        { class: "dr-foot" },
        h(
          "button",
          { class: "cp-btn cp-btn-primary", style: { flex: 1, "justify-content": "center" } },
          Ic.user(16),
          "Assigner à un journaliste",
        ),
        h("button", { class: "cp-btn cp-btn-ghost" }, Ic.bookmark(16), "À traiter"),
      ),
    ),
  );
};

/* ---------- Filtre + tri ---------- */

const computeVisible = () => {
  let list = state.topics.slice();
  if (state.catFilter) list = list.filter((t) => t.cat === state.catFilter);
  if (state.query) {
    const q = state.query.toLowerCase();
    list = list.filter((t) => {
      const hay = (t.title + " " + t.entities.join(" ") + " " + (CATEGORIES[t.cat]?.label || "")).toLowerCase();
      return hay.includes(q);
    });
  }
  if (state.railFilter) {
    const q = state.railFilter.toLowerCase();
    list = list.filter((t) => {
      const hay = (t.title + " " + t.entities.join(" ") + " " + (CATEGORIES[t.cat]?.label || "")).toLowerCase();
      return hay.includes(q);
    });
  }
  if (state.sort === "rising") list.sort((a, b) => b.delta - a.delta || a.rank - b.rank);
  else if (state.sort === "recent") list.sort((a, b) => b.rank - a.rank);
  else list.sort((a, b) => a.rank - b.rank);
  return list;
};

/* ---------- Render principal ---------- */

const render = () => {
  const root = document.getElementById("cp-root");
  if (!root) return;
  root.innerHTML = "";

  root.appendChild(renderTopNav());
  root.appendChild(renderTodayBar());

  const container = h("div", { class: "cp-container" });
  container.appendChild(renderKpiRow());
  container.appendChild(renderHero());

  const visible = computeVisible();
  const filtering = state.catFilter || state.query || state.railFilter;

  const main = h(
    "div",
    {},
    h(
      "div",
      { class: "sec-head" },
      h("span", { class: "sec-title" }, "Classement du jour"),
      h("span", { class: "sec-sub" }, "trié par signal score"),
      h("span", { class: "sec-count" }, `${visible.length} / ${state.topics.length}`),
    ),
    renderToolbar(),
    state.railFilter
      ? h(
          "div",
          { style: { display: "flex", "align-items": "center", gap: "10px", "margin-bottom": "14px" } },
          h(
            "span",
            { class: "chip on" },
            `Filtre : ${state.railFilter}`,
            h(
              "button",
              {
                onClick: (e) => {
                  e.stopPropagation();
                  setState({ railFilter: null });
                },
                style: { display: "grid", "place-items": "center", "margin-left": "2px", background: "none", border: "none", color: "currentColor", cursor: "pointer" },
              },
              Ic.x(12),
            ),
          ),
          h(
            "button",
            {
              class: "clearfilter",
              onClick: () => setState({ catFilter: null, query: "", railFilter: null }),
            },
            "Tout effacer",
          ),
        )
      : null,
    renderList(visible),
  );

  const layout = h("div", { class: "layout" }, main, renderRail());
  container.appendChild(layout);

  root.appendChild(container);

  if (state.drawer) root.appendChild(renderDrawer(state.drawer));
};

/* ---------- Mount ---------- */

const mount = async () => {
  // Initial empty render
  render();

  let raw;
  try {
    const data = await loadSujets();
    raw = {
      generated_at: data.generatedAt,
      sources_used: data.sources,
      sujets: data.sujets,
      categories_trending: data.categoriesTrending,
      entity_clusters: data.entityClusters,
      entities_trending: data.entitiesTrending,
    };
  } catch (err) {
    console.error("Failed to load sujets:", err);
    document.getElementById("cp-root").innerHTML = `<div style="padding:60px;text-align:center;color:var(--fg-muted);">Erreur de chargement. Recharge la page ou lance le pipeline.</div>`;
    return;
  }

  state.raw = raw;
  state.topics = (raw.sujets || []).map(adaptSujet);
  render();

  // Charge evolution en arrière-plan et injecte les deltas si possible
  const evo = await tryLoadEvolution();
  if (evo?.available) {
    state.evo = evo;
    // Tente d'injecter un delta par titre_hash si on a un mapping (sujets_persistance)
    const byHash = {};
    for (const s of evo.sujets_persistance || []) byHash[s.title_hash] = s;
    // SHA-256 du titre normalisé côté front : on n'a pas crypto facilement, on
    // fait un simple match par normalisation du titre.
    const norm = (s) =>
      (s || "")
        .toString()
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^\w\s]/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 60);
    const byTitle = {};
    for (const s of evo.sujets_persistance || []) {
      byTitle[norm(s.title)] = s;
    }
    for (const t of state.topics) {
      const m = byTitle[norm(t.title)];
      if (m) {
        t.delta = m.score_delta || 0;
      }
    }
    render();
  }

  // Esc ferme le drawer
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.drawer) setState({ drawer: null });
    if (e.key === "/" && !state.drawer) {
      const input = document.querySelector(".nav-search input");
      if (input && document.activeElement !== input) {
        e.preventDefault();
        input.focus();
      }
    }
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
