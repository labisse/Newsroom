/* ============================================================
   EDITORIAL SIGNAL — Catégories (design Claude, vanilla)
   Vue cross-source par grande thématique éditoriale.
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

/* ---------- Lucide-like icons pour catégories ---------- */
const CAT_ICON = {
  // Politique : monument antique
  landmark: () => svgEl(
    '<path d="M3 22h18M5 10v9M9 10v9M15 10v9M19 10v9M3 6l9-4 9 4v3H3V6Z"/>',
  ),
  // International : globe
  globe: () => svgEl(
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  ),
  // Économie : pièces
  coins: () => svgEl(
    '<circle cx="8" cy="8" r="5"/><path d="M11 12.5a5 5 0 1 0 5.5 6.5"/><path d="M5.5 8.5h5"/>',
  ),
  // Tech : processeur
  cpu: () => svgEl(
    '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  ),
  // Sport : trophée
  trophy: () => svgEl(
    '<path d="M7 4h10v6a5 5 0 0 1-10 0V4Z"/><path d="M7 7H4a2 2 0 0 0 0 4h3M17 7h3a2 2 0 0 1 0 4h-3"/><path d="M10 17h4M12 14v3M8 21h8"/>',
  ),
  // Divertissement : étoile 4 branches
  sparkle: () => svgEl(
    '<path d="M12 3l1.8 6.2L20 11l-6.2 1.8L12 19l-1.8-6.2L4 11l6.2-1.8L12 3Z"/>',
  ),
  // Science : atome
  atom: () => svgEl(
    '<circle cx="12" cy="12" r="2"/><ellipse cx="12" cy="12" rx="10" ry="4.5"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(-60 12 12)"/>',
  ),
  // Santé : coeur
  heart: () => svgEl(
    '<path d="M12 20s-7-4.5-9-9a4.5 4.5 0 0 1 9-2 4.5 4.5 0 0 1 9 2c-2 4.5-9 9-9 9Z"/>',
  ),
  // Société : users
  users: () => svgEl(
    '<circle cx="9" cy="8" r="3.5"/><path d="M3 21c0-3 3-5 6-5s6 2 6 5"/><circle cx="17" cy="9" r="3"/><path d="M14 21c0-2 2-4 6-4"/>',
  ),
  // Lifestyle : feuille
  leaf: () => svgEl(
    '<path d="M3 21c0-9 7-16 18-17 0 11-7 17-18 17"/><path d="M3 21c5-5 9-9 14-12"/>',
  ),
};

/* ---------- Source glyphs ---------- */
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

const Ic = {
  search: () => svgEl('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>', 18, 18),
  x: () => svgEl('<path d="M6 6l12 12M18 6 6 18"/>', 14, 14),
};

const HUE = {
  indigo: "#818CF8",
  pink: "#F472B6",
  emerald: "#34D399",
  purple: "#C084FC",
  amber: "#FBBF24",
  blue: "#60A5FA",
  red: "#FB7185",
};

const SRC_HUE = {
  discover: "indigo",
  gnews: "blue",
  msn: "indigo",
  trends: "emerald",
  wiki: "purple",
  youtube: "red",
  x: "blue",
  reddit: "amber",
};

const SRC_LABEL = {
  discover: "Discover",
  gnews: "Google News",
  msn: "MSN",
  trends: "Google Trends",
  wiki: "Wikipédia",
  youtube: "YouTube",
  x: "X",
  reddit: "Reddit",
};

/* ---------- Catégories canoniques ---------- */
const CATEGORIES = [
  { key: "politique", label: "Politique", icon: "landmark", hue: "indigo" },
  { key: "international", label: "International", icon: "globe", hue: "blue" },
  { key: "economie", label: "Économie", icon: "coins", hue: "amber" },
  { key: "tech", label: "Tech & Numérique", icon: "cpu", hue: "purple" },
  { key: "sport", label: "Sport", icon: "trophy", hue: "emerald" },
  { key: "people", label: "Divertissement & People", icon: "sparkle", hue: "pink" },
  { key: "science", label: "Science", icon: "atom", hue: "blue" },
  { key: "sante", label: "Santé", icon: "heart", hue: "red" },
  { key: "societe", label: "Société", icon: "users", hue: "indigo" },
  { key: "lifestyle", label: "Lifestyle", icon: "leaf", hue: "emerald" },
];

/* ---------- Classifieurs (repris depuis l'ancienne version) ---------- */

const classifyDiscover = (item) => {
  const c = item.category || "";
  if (c.startsWith("/News/Politics")) return "politique";
  if (c.startsWith("/News/World News")) return "international";
  if (c.startsWith("/News/Business News")) return "economie";
  if (c.startsWith("/News/Sports News")) return "sport";
  if (c.startsWith("/Law & Government")) return "politique";
  if (c.startsWith("/Sports")) return "sport";
  if (c.startsWith("/Arts & Entertainment")) return "people";
  if (c.startsWith("/Health")) return "sante";
  if (c.startsWith("/Beauty & Fitness")) return "sante";
  if (c.startsWith("/Science")) return "science";
  if (c.startsWith("/Computers")) return "tech";
  if (c.startsWith("/Internet")) return "tech";
  if (c.startsWith("/Finance")) return "economie";
  if (c.startsWith("/Business & Industrial")) return "economie";
  if (c.startsWith("/Food")) return "lifestyle";
  if (c.startsWith("/Travel")) return "lifestyle";
  if (c.startsWith("/Home")) return "lifestyle";
  if (c.startsWith("/Autos")) return "lifestyle";
  if (c.startsWith("/Pets")) return "lifestyle";
  if (c.startsWith("/Hobbies")) return "lifestyle";
  if (c.startsWith("/People")) return "societe";
  if (c.startsWith("/Sensitive")) return "societe";
  if (c.startsWith("/News")) return "societe";
  return null;
};

const classifyGnews = (item) => {
  const c = (item.category || "").toLowerCase();
  return {
    politique: "politique",
    international: "international",
    economie: "economie",
    technologie: "tech",
    sports: "sport",
    divertissement: "people",
    science: "science",
    sante: "sante",
    france: "societe",
  }[c];
};

const classifyMsn = (item) => {
  const c = (item.category || "").toLowerCase();
  if (c.includes("politique")) return "politique";
  if (c.includes("sport")) return "sport";
  if (c.includes("divertissement")) return "people";
  if (c.includes("lifestyle") || c.includes("style")) return "lifestyle";
  if (c.includes("finance") || c.startsWith("eco")) return "economie";
  if (c.includes("tech") || c.includes("numer")) return "tech";
  if (c.includes("sante")) return "sante";
  if (c.includes("science")) return "science";
  if (c.includes("monde") || c.includes("inter")) return "international";
  if (c === "actualite") return "societe";
  return null;
};

const REDDIT_SUB_MAP = {
  france: "societe", actualite: "societe", AskFrance: "societe",
  francepolitique: "politique", Politique: "politique",
  europe: "international",
  sciences: "science", Histoire: "science",
  technologie: "tech",
  jeuxvideo: "people", cinema_francais: "people", musique: "people", musiquefrancaise: "people",
  Cuisine: "lifestyle", cuisine: "lifestyle",
  sport_FR: "sport",
};

const YOUTUBE_CAT_MAP = {
  "Actualités & politique": "politique",
  Sport: "sport",
  "Sciences & tech": "tech",
  "Films & animation": "people",
  Musique: "people",
  Divertissement: "people",
  Comédie: "people",
  Vlogs: "lifestyle",
  "Conseils & style": "lifestyle",
  Éducation: "science",
  "Jeux vidéo": "people",
};

/* ---------- normalisation /65 ---------- */
const heatColor = (s) => {
  if (s >= 28) return "var(--hot)";
  if (s >= 11) return "var(--warm)";
  return "var(--cool)";
};

const normalizeScore = (raw, idx, total) => {
  if (raw != null && raw > 0) return Math.min(65, Math.max(0, Number(raw)));
  const t = total > 1 ? idx / (total - 1) : 0;
  return Math.round((60 - t * 55) * 10) / 10;
};

const fmtVol = (n, suffix = "") => {
  const v = Number(n) || 0;
  if (!v) return "0" + suffix;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M${suffix}`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}k${suffix}`;
  return `${v}${suffix}`;
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

const todayFr = () => {
  const d = new Date();
  const long = d.toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return long.charAt(0).toUpperCase() + long.slice(1);
};

/* ---------- chargement + classification ---------- */

const state = {
  raw: {},
  // par catégorie : { items: [], breakdown: [[src, n], ...], count }
  byCat: {},
  active: "politique",
  src: null, // filtre source
  query: "",
  fetched_at: null, // plus ancien fetched_at pour la barre "MAJ"
};

const setState = (patch) => {
  Object.assign(state, patch);
  render();
};

const loadAll = async () => {
  const sources = [
    { key: "discover", file: "discoversnoop" },
    { key: "gnews", file: "google_news" },
    { key: "reddit", file: "reddit" },
    { key: "youtube", file: "youtube_trending" },
    { key: "trends", file: "google_trends" },
    { key: "msn", file: "msn" },
  ];
  await Promise.all(
    sources.map(async (s) => {
      try {
        const r = await fetch(`data/${s.file}/latest.json`, { cache: "no-store" });
        if (r.ok) state.raw[s.key] = await r.json();
      } catch {
        // ignore
      }
    }),
  );

  // Trouve le plus récent fetched_at parmi les sources chargées
  let latest = null;
  for (const v of Object.values(state.raw)) {
    if (v?.fetched_at) {
      if (!latest || v.fetched_at > latest) latest = v.fetched_at;
    }
  }
  state.fetched_at = latest;

  classifyAll();
};

const classifyAll = () => {
  // Init buckets vides
  const buckets = {};
  for (const c of CATEGORIES) {
    buckets[c.key] = { items: [], srcCounts: {} };
  }

  const pushItem = (catKey, src, item) => {
    if (!buckets[catKey]) return;
    buckets[catKey].items.push({ ...item, src });
    buckets[catKey].srcCounts[src] = (buckets[catKey].srcCounts[src] || 0) + 1;
  };

  // Discover
  const dArts = (state.raw.discover?.articles || []).slice();
  dArts.sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0));
  dArts.forEach((a, i) => {
    const cat = classifyDiscover(a);
    if (!cat) return;
    pushItem(cat, "discover", {
      score: Number(a.score) || 0.5,
      title: a.title || "(sans titre)",
      pub: a.publisher || "—",
      tags: (a.category || "").split("/").filter(Boolean).slice(-2),
      metric: null,
      url: a.url,
    });
  });

  // GNews
  const gArts = state.raw.gnews?.articles || [];
  gArts.forEach((a, i) => {
    const cat = classifyGnews(a);
    if (!cat) return;
    pushItem(cat, "gnews", {
      score: normalizeScore(null, i, gArts.length),
      title: a.title,
      pub: a.source || "Google News",
      tags: a.category ? [a.category] : [],
      metric: null,
      url: a.url,
    });
  });

  // MSN
  const mArts = (state.raw.msn?.articles || []).slice();
  mArts.sort((a, b) => {
    const ae = (a.upvotes || 0) + (a.comments || 0) * 2;
    const be = (b.upvotes || 0) + (b.comments || 0) * 2;
    return be - ae;
  });
  mArts.forEach((a, i) => {
    const cat = classifyMsn(a);
    if (!cat) return;
    const engagement = (a.upvotes || 0) + (a.comments || 0);
    pushItem(cat, "msn", {
      score: normalizeScore(null, i, mArts.length),
      title: a.title,
      pub: a.source || "MSN",
      tags: a.category ? [a.category] : [],
      metric: engagement > 0 ? `${engagement} réactions` : null,
      url: a.url,
    });
  });

  // Reddit
  const rPosts = (state.raw.reddit?.posts || []).slice();
  rPosts.sort(
    (a, b) =>
      (b.score || 0) - (a.score || 0) ||
      (b.cross_subs_count || 1) - (a.cross_subs_count || 1),
  );
  rPosts.forEach((p, i) => {
    const cat = REDDIT_SUB_MAP[p.subreddit];
    if (!cat) return;
    pushItem(cat, "reddit", {
      score: normalizeScore(null, i, rPosts.length),
      title: p.title,
      pub: `r/${p.subreddit}`,
      tags:
        p.cross_subs && p.cross_subs.length > 1
          ? [`${p.cross_subs.length} subs`]
          : p.domain
            ? [p.domain]
            : [],
      metric: p.score
        ? `${fmtVol(p.score)} upvotes`
        : p.cross_subs_count > 1
          ? `×${p.cross_subs_count} subs`
          : null,
      url: p.url || p.permalink,
    });
  });

  // YouTube
  const yVids = (state.raw.youtube?.videos || []).slice();
  yVids.sort((a, b) => (b.velocity_views_per_hour || 0) - (a.velocity_views_per_hour || 0));
  yVids.forEach((v, i) => {
    const cat = YOUTUBE_CAT_MAP[v.category_label];
    if (!cat) return;
    pushItem(cat, "youtube", {
      score: normalizeScore(null, i, yVids.length),
      title: v.title,
      pub: v.channel || "YouTube",
      tags: v.category_label ? [v.category_label] : [],
      metric: v.velocity_views_per_hour
        ? `${fmtVol(v.velocity_views_per_hour)} vues/h`
        : v.views
          ? `${fmtVol(v.views)} vues`
          : null,
      url: v.url,
    });
  });

  // Compute final byCat avec breakdown ordonné par count desc
  state.byCat = {};
  for (const c of CATEGORIES) {
    const b = buckets[c.key];
    const breakdown = Object.entries(b.srcCounts).sort((a, b) => b[1] - a[1]);
    state.byCat[c.key] = {
      items: b.items,
      breakdown,
      count: b.items.length,
    };
  }
};

/* ---------- recherche ---------- */
const norm = (s) =>
  (s || "")
    .toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

const filterItems = (items) => {
  let out = items.slice();
  if (state.src) out = out.filter((it) => it.src === state.src);
  if (state.query) {
    const q = norm(state.query);
    out = out.filter((it) => {
      const hay = norm(
        `${it.title} ${it.pub || ""} ${(it.tags || []).join(" ")} ${it.metric || ""}`,
      );
      return hay.includes(q);
    });
  }
  out.sort((a, b) => b.score - a.score);
  return out;
};

/* ---------- renderers ---------- */

const renderHero = () =>
  h(
    "section",
    { class: "tp-hero" },
    h(
      "div",
      { class: "tp-eyebrow" },
      h("span", { class: "dot" }),
      "Tendances par catégorie ",
      h("span", { class: "muted" }, `· ${todayFr()}`),
    ),
    h(
      "h1",
      { class: "tp-title" },
      "Ce qui buzze ",
      h("span", { class: "accent" }, "par thématique"),
    ),
    h(
      "p",
      { class: "tp-sub" },
      "Vue cross-source par grande catégorie éditoriale — chaque onglet agrège les items de toutes les sources qui couvrent la thématique.",
    ),
  );

const renderFilter = () =>
  h(
    "div",
    { class: "tp-filterbar" },
    h(
      "div",
      { class: "tp-filter-input" },
      (() => {
        const s = Ic.search();
        s.style.color = "var(--fg-subtle)";
        return s;
      })(),
      h("input", {
        value: state.query,
        placeholder: "Filtrer par mot-clé dans la catégorie active…",
        type: "search",
        oninput: (e) => setState({ query: e.target.value }),
      }),
      state.query
        ? h(
            "button",
            {
              class: "tp-filter-clear",
              onClick: () => setState({ query: "" }),
            },
            Ic.x(),
          )
        : null,
    ),
  );

const renderTabs = () => {
  const wrap = h("div", { class: "tp-tabs" });
  for (const c of CATEGORIES) {
    const I = CAT_ICON[c.icon];
    const count = state.byCat[c.key]?.count || 0;
    const isOn = c.key === state.active;
    wrap.appendChild(
      h(
        "button",
        {
          class: "tp-tab" + (isOn ? " on" : "") + (count === 0 ? " zero" : ""),
          style: { "--tab-c": HUE[c.hue] },
          onClick: () => setState({ active: c.key, src: null, query: "" }),
        },
        h("span", { class: "tp-tab-ic cat" }, I ? I() : null),
        h("span", { class: "tp-tab-label" }, c.label),
        h("span", { class: "tp-tab-count" }, String(count)),
      ),
    );
  }
  return wrap;
};

const renderListbar = (cat, visibleCount, totalCount) =>
  h(
    "div",
    { class: "tp-listbar" },
    h(
      "span",
      { class: "tp-items" },
      h("span", { class: "pf-dot", style: { background: HUE[cat.hue] } }),
      state.src || state.query
        ? `${visibleCount} résultat${visibleCount > 1 ? "s" : ""} / ${totalCount}`
        : `${totalCount} items dans ${cat.label}`,
    ),
    h(
      "span",
      { class: "tp-upd" },
      h("span", { class: "live-dot" }),
      `Mis à jour ${fmtAgo(state.fetched_at)}`,
    ),
  );

const renderMixbar = (breakdown) => {
  if (!breakdown.length) return null;
  const wrap = h("div", { class: "cp-mixwrap" });
  const bar = h("div", { class: "cp-mixbar" });
  for (const [src, n] of breakdown) {
    bar.appendChild(
      h("i", {
        class: state.src && state.src !== src ? "dim" : "",
        title: `${SRC_LABEL[src]} · ${n}`,
        style: { flex: String(n), background: HUE[SRC_HUE[src]] },
      }),
    );
  }
  wrap.appendChild(bar);
  return wrap;
};

const renderSrcFilters = (cat, breakdown) => {
  const total = breakdown.reduce((s, [, n]) => s + n, 0);
  const wrap = h(
    "div",
    { class: "cp-srcfilters" },
    h("span", { class: "lbl" }, "Sources"),
  );
  wrap.appendChild(
    h(
      "button",
      {
        class: "cp-srcchip" + (state.src === null ? " on" : ""),
        style: { "--sc-c": HUE[cat.hue] },
        onClick: () => setState({ src: null }),
      },
      "Toutes ",
      h("span", { class: "n" }, String(total)),
    ),
  );
  for (const [src, n] of breakdown) {
    const G = SRC_GLYPH[src];
    wrap.appendChild(
      h(
        "button",
        {
          class: "cp-srcchip" + (state.src === src ? " on" : ""),
          style: { "--sc-c": HUE[SRC_HUE[src]] },
          onClick: () => setState({ src: state.src === src ? null : src }),
        },
        h("span", { class: "gl" }, G ? G() : null),
        SRC_LABEL[src] || src,
        h("span", { class: "n" }, String(n)),
      ),
    );
  }
  return wrap;
};

const renderRow = (item, rank) => {
  const c = heatColor(item.score);
  const G = SRC_GLYPH[item.src];
  const srcColor = HUE[SRC_HUE[item.src]] || "var(--fg-muted)";
  const scoreTxt = Number.isInteger(item.score)
    ? String(item.score)
    : item.score.toFixed(1);
  const tag = item.url ? "a" : "div";
  const linkAttrs = item.url
    ? { href: item.url, target: "_blank", rel: "noopener noreferrer" }
    : {};
  const meta = h(
    "div",
    { class: "tp-row-meta" },
    h(
      "span",
      {
        class: "cp-srcbadge",
        title: SRC_LABEL[item.src] || item.src,
      },
      (() => {
        if (!G) return null;
        const el = G();
        el.style.color = srcColor;
        return el;
      })(),
    ),
    h("span", { class: "tp-pub" }, item.pub),
    ...(item.tags && item.tags.length
      ? item.tags.flatMap((t) => [
          h("span", { class: "tp-metasep" }, "·"),
          h("span", { class: "tp-tag" }, t),
        ])
      : []),
  );
  return h(
    tag,
    {
      class: "tp-row tp-fade-up",
      style: {
        "--spine": c,
        "animation-delay": Math.min(rank, 14) * 22 + "ms",
      },
      ...linkAttrs,
    },
    h("div", { class: "tp-row-rank" }, String(rank).padStart(2, "0")),
    h(
      "div",
      {
        class: "tp-scorepill",
        style: {
          "border-color": `color-mix(in srgb, ${c} 38%, var(--line-2))`,
        },
      },
      h("span", { class: "tp-sp-num", style: { color: c } }, scoreTxt),
      h("span", { class: "tp-sp-den" }, "/ 65"),
    ),
    h(
      "div",
      { class: "tp-row-mid" },
      h("div", { class: "tp-row-title" }, item.title),
      meta,
    ),
    h(
      "div",
      { class: "tp-row-right" },
      item.metric ? h("span", { class: "tp-metric-chip" }, item.metric) : null,
    ),
  );
};

const renderList = (items) => {
  if (!items.length) return null;
  const wrap = h("div", { class: "tp-list" });
  items.slice(0, 100).forEach((it, i) => wrap.appendChild(renderRow(it, i + 1)));
  return wrap;
};

const renderEmpty = (cat) =>
  h(
    "div",
    { class: "tp-empty" },
    h(
      "div",
      { class: "tp-empty-card" },
      h("div", { class: "tp-empty-ic" }, Ic.search()),
      h(
        "h3",
        {},
        state.query
          ? "Aucun résultat"
          : `Aucun item en ${cat.label} aujourd'hui`,
      ),
      state.query
        ? h(
            "p",
            {},
            `Aucun item ne correspond à « ${state.query} » dans ${cat.label}. `,
            h(
              "button",
              {
                class: "clearfilter",
                onClick: () => setState({ query: "", src: null }),
              },
              "Réinitialiser",
            ),
          )
        : h(
            "p",
            {},
            "Aucune source n'a remonté de contenu dans cette catégorie sur la fenêtre en cours. Les items réapparaîtront au prochain passage du pipeline.",
          ),
    ),
  );

/* ---------- render principal ---------- */
const render = () => {
  const root = document.getElementById("cp-root");
  if (!root) return;
  root.innerHTML = "";

  root.appendChild(renderHero());
  root.appendChild(renderFilter());
  root.appendChild(renderTabs());

  const cat = CATEGORIES.find((c) => c.key === state.active);
  const bucket = state.byCat[cat.key] || { items: [], breakdown: [], count: 0 };
  const visible = filterItems(bucket.items);

  root.appendChild(renderListbar(cat, visible.length, bucket.count));
  const mb = renderMixbar(bucket.breakdown);
  if (mb) root.appendChild(mb);
  if (bucket.breakdown.length) {
    root.appendChild(renderSrcFilters(cat, bucket.breakdown));
  }

  if (visible.length === 0) {
    root.appendChild(renderEmpty(cat));
  } else {
    root.appendChild(renderList(visible));
  }
};

/* ---------- mount ---------- */
const mount = async () => {
  render(); // squelette
  await loadAll();

  // Choisit la catégorie la mieux dotée par défaut
  let best = "politique";
  let max = -1;
  for (const c of CATEGORIES) {
    const n = state.byCat[c.key]?.count || 0;
    if (n > max) {
      max = n;
      best = c.key;
    }
  }
  state.active = best;
  render();

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName || "")) {
      const input = document.querySelector(".tp-filter-input input");
      if (input) {
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
