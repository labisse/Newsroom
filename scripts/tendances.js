/* ============================================================
   EDITORIAL SIGNAL — Tendances par source (design Claude, vanilla)
   Branche les vraies données data/{source}/latest.json sur le design
   "encre éditoriale élevée".
   ============================================================ */

/* ---------- helpers DOM ---------- */
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

const svgEl = (paths, w = 18, hp = 18) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "2");
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("width", String(w));
  s.setAttribute("height", String(hp));
  s.innerHTML = paths;
  return s;
};

const Ic = {
  search: () => svgEl('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>', 18, 18),
  x: () => svgEl('<path d="M6 6l12 12M18 6 6 18"/>', 14, 14),
  link: () => svgEl(
    '<path d="M9 14a4 4 0 0 0 6 0l2-2a4 4 0 0 0-6-6l-1 1"/><path d="M15 10a4 4 0 0 0-6 0l-2 2a4 4 0 0 0 6 6l1-1"/>',
    15,
    15,
  ),
};

const SRC_GLYPH = {
  discover: () => svgEl(
    '<circle cx="12" cy="12" r="8"/><path d="m9 15 1.5-4.5L15 9l-1.5 4.5L9 15Z" fill="currentColor" stroke="none"/>',
    18,
    18,
  ),
  gnews: () => svgEl('<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 12h8M8 15h5"/>', 18, 18),
  trends: () => svgEl('<path d="m4 16 5-5 3 3 7-7"/><path d="M16 7h4v4"/>', 18, 18),
  wiki: () => svgEl('<path d="M3 7 7 17 10.5 9 14 17 21 7"/>', 18, 18),
  msn: () => svgEl('<path d="M4 18V7l4 6 4-6 4 6 4-6v11"/>', 18, 18),
  x: () => svgEl('<path d="M5 5l14 14M19 5 5 19"/>', 18, 18),
  reddit: () => svgEl(
    '<circle cx="12" cy="13" r="7"/><circle cx="12" cy="4" r="1.4"/><path d="M12 5.5V9"/><circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none"/><path d="M9.5 16c1.5 1 3.5 1 5 0"/>',
    18,
    18,
  ),
  youtube: () => svgEl(
    '<rect x="3" y="6" width="18" height="12" rx="3"/><path d="m10.5 9.5 4 2.5-4 2.5Z" fill="currentColor" stroke="none"/>',
    18,
    18,
  ),
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

/* ---------- plateformes ----------
 * Reddit retire du selecteur : source desactivee en CI (reCAPTCHA bloque
 * la creation d'app OAuth + RSS blackliste sur IPs GitHub Actions).
 * Adapter conserve plus bas pour reactivation future. */
const PLATFORMS = [
  { key: "discover", file: "discoversnoop", label: "Discover", glyph: "discover", hue: "indigo" },
  { key: "gnews", file: "google_news", label: "Google News", glyph: "gnews", hue: "blue" },
  { key: "youtube", file: "youtube_trending", label: "YouTube", glyph: "youtube", hue: "red" },
  { key: "trends", file: "google_trends", label: "Google Trends", glyph: "trends", hue: "emerald" },
  { key: "wiki", file: "wikimedia", label: "Wikipédia", glyph: "wiki", hue: "purple" },
  { key: "x", file: "x_trends", label: "X (Twitter)", glyph: "x", hue: "blue" },
  { key: "msn", file: "msn", label: "MSN", glyph: "msn", hue: "indigo" },
];

/* ---------- helpers chaleur (echelle /100, rescale x1.2) ----------
   Seuils hot/warm alignes sur le rescale 28/11 internal -> 34/13. */
const heatColor = (score) => {
  if (score >= 34) return "var(--hot)";
  if (score >= 13) return "var(--warm)";
  return "var(--cool)";
};

const fmtVol = (n, suffix = "") => {
  const v = Number(n) || 0;
  if (!v) return suffix ? `0${suffix}` : "0";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M${suffix}`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}k${suffix}`;
  return `${v}${suffix}`;
};

/* ---------- normalisation par plateforme ----------
   Discover CSV est /65 nativement. Rescale x1.2 (meme facteur que
   l'aggregator backend) : 65 -> 78, 50 -> 60, 30 -> 36. 100 reste
   exceptionnel (~ Discover score brut 84+, jamais observe).
   Plateformes sans score brut : interpolation par rang (72 -> 5). */

const normalizeScore = (rawScore, idx, total) => {
  if (rawScore != null && rawScore > 0) {
    return Math.min(100, Math.max(0, Number(rawScore) * 1.2));
  }
  const t = total > 1 ? idx / (total - 1) : 0;
  return Math.round((72 - t * 67) * 10) / 10;
};

/* ---------- adapters per source ---------- */

const adaptDiscover = (data) => {
  const arts = [...(data.articles || [])].sort(
    (a, b) => (Number(b.score) || 0) - (Number(a.score) || 0),
  );
  return arts.map((a, i) => ({
    score: Number(a.score) || 0.5,
    title: a.title || "(sans titre)",
    pub: a.publisher || "—",
    tags: (a.category || "")
      .split("/")
      .filter(Boolean)
      .slice(-2),
    metric: null,
    url: a.url,
  }));
};

const adaptGnews = (data) => {
  const arts = data.articles || [];
  return arts.map((a, i) => ({
    score: normalizeScore(null, i, arts.length),
    title: a.title,
    pub: a.source || "Google News",
    tags: a.category ? [a.category] : [],
    metric: a.published_at ? null : null,
    url: a.url,
  }));
};

const adaptReddit = (data) => {
  const posts = [...(data.posts || [])].sort(
    (a, b) =>
      (b.score || 0) - (a.score || 0) ||
      (b.cross_subs_count || 1) - (a.cross_subs_count || 1),
  );
  return posts.map((p, i) => ({
    score: normalizeScore(null, i, posts.length),
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
  }));
};

const adaptYoutube = (data) => {
  const vids = [...(data.videos || [])].sort(
    (a, b) => (b.velocity_views_per_hour || 0) - (a.velocity_views_per_hour || 0),
  );
  return vids.map((v, i) => ({
    score: normalizeScore(null, i, vids.length),
    title: v.title,
    pub: v.channel || "YouTube",
    tags: v.category_label ? [v.category_label] : [],
    metric: v.velocity_views_per_hour
      ? `${fmtVol(v.velocity_views_per_hour)} vues/h`
      : v.views
        ? `${fmtVol(v.views)} vues`
        : null,
    url: v.url,
  }));
};

const adaptTrends = (data) => {
  const trends = ((data.windows && data.windows.current) || {}).trends || [];
  return trends.map((t, i) => ({
    score: normalizeScore(null, i, trends.length),
    title: t.query || "—",
    pub: (t.categories && t.categories[0]) || "Trends",
    tags: t.percentage_increase
      ? [`+${t.percentage_increase}%`]
      : t.categories && t.categories.length > 1
        ? [t.categories[1]]
        : [],
    metric: t.search_volume ? `${fmtVol(t.search_volume)} recherches` : null,
    url: null,
  }));
};

const adaptWiki = (data) => {
  const arts = data.articles || [];
  const project = data.project || "fr.wikipedia";
  const projectDomain = project.includes(".")
    ? `${project.split(".")[0]}.wikipedia.org`
    : "fr.wikipedia.org";
  return arts.map((a, i) => ({
    score: normalizeScore(null, i, arts.length),
    title: a.title_display || a.article || "—",
    pub: project,
    tags: [],
    metric: a.views ? `${fmtVol(a.views)} vues` : null,
    url: a.article ? `https://${projectDomain}/wiki/${a.article}` : null,
  }));
};

const adaptX = (data) => {
  const trends = data.trends || [];
  return trends.map((t, i) => ({
    score: normalizeScore(null, i, trends.length),
    title: t.query || t.name || "—",
    pub: `Tendance #${i + 1}`,
    tags: [],
    metric: t.tweet_count
      ? `${fmtVol(t.tweet_count)} posts`
      : `#${i + 1} France`,
    url: null,
  }));
};

const adaptMsn = (data) => {
  const arts = [...(data.articles || [])].sort(
    (a, b) => {
      const ae = (a.upvotes || 0) + (a.comments || 0) * 2;
      const be = (b.upvotes || 0) + (b.comments || 0) * 2;
      return be - ae;
    },
  );
  return arts.map((a, i) => {
    const engagement = (a.upvotes || 0) + (a.comments || 0);
    return {
      score: normalizeScore(null, i, arts.length),
      title: a.title,
      pub: a.source || "MSN",
      tags: a.category ? [a.category] : [],
      metric: engagement > 0 ? `${engagement} réactions` : null,
      url: a.url,
    };
  });
};

const ADAPTERS = {
  discover: adaptDiscover,
  gnews: adaptGnews,
  reddit: adaptReddit,
  youtube: adaptYoutube,
  trends: adaptTrends,
  wiki: adaptWiki,
  x: adaptX,
  msn: adaptMsn,
};

/* ---------- state ---------- */
const state = {
  raw: {}, // par platform key
  items: {}, // adaptés
  counts: {}, // total brut par plateforme
  active: "discover",
  query: "",
  fetched_at: {},
};

const setState = (patch) => {
  Object.assign(state, patch);
  render();
};

/* ---------- chargement ---------- */
const loadPlatform = async (pf) => {
  if (state.raw[pf.key]) return;
  try {
    const r = await fetch(`data/${pf.file}/latest.json`, { cache: "no-store" });
    if (!r.ok) {
      state.raw[pf.key] = { error: `HTTP ${r.status}` };
      state.items[pf.key] = [];
      state.counts[pf.key] = 0;
      return;
    }
    const data = await r.json();
    state.raw[pf.key] = data;
    state.items[pf.key] = ADAPTERS[pf.key] ? ADAPTERS[pf.key](data) : [];
    state.counts[pf.key] = state.items[pf.key].length;
    state.fetched_at[pf.key] = data.fetched_at;
  } catch (e) {
    state.raw[pf.key] = { error: e.message };
    state.items[pf.key] = [];
    state.counts[pf.key] = 0;
  }
};

const loadAll = async () => {
  await Promise.all(PLATFORMS.map(loadPlatform));
};

/* ---------- format relatif ---------- */
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

/* ---------- renderers ---------- */

const renderHero = () =>
  h(
    "section",
    { class: "tp-hero" },
    h(
      "div",
      { class: "tp-eyebrow" },
      h("span", { class: "dot" }),
      "Tendances par source ",
      h("span", { class: "muted" }, `· ${todayFr()}`),
    ),
    h(
      "h1",
      { class: "tp-title" },
      "Ce qui buzze ",
      h("span", { class: "accent" }, "par plateforme"),
    ),
    h(
      "p",
      { class: "tp-sub" },
      "Vue brute, signal par signal — pour repérer les angles qui marchent sur chaque support, sans passer par le scoring agrégé.",
    ),
  );

const renderFilterbar = () => {
  const input = h("input", {
    value: state.query,
    placeholder: "Filtrer par mot-clé (ex : bardella, climat, roland-garros…)",
    type: "search",
    oninput: (e) => setState({ query: e.target.value }),
  });
  return h(
    "div",
    { class: "tp-filterbar" },
    h(
      "div",
      { class: "tp-filter-input" },
      (() => {
        const s = Ic.search();
        s.style.color = "var(--fg-subtle)";
        s.style.flexShrink = "0";
        return s;
      })(),
      input,
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
};

const renderTabs = () => {
  const wrap = h("div", { class: "tp-tabs" });
  for (const pf of PLATFORMS) {
    const count = state.counts[pf.key] || 0;
    const isOn = pf.key === state.active;
    const G = SRC_GLYPH[pf.glyph];
    wrap.appendChild(
      h(
        "button",
        {
          class:
            "tp-tab" +
            (isOn ? " on" : "") +
            (count === 0 ? " zero" : ""),
          style: { "--tab-c": HUE[pf.hue] },
          onClick: () => setState({ active: pf.key }),
        },
        h("span", { class: "tp-tab-ic" }, G ? G() : null),
        h("span", { class: "tp-tab-label" }, pf.label),
        h("span", { class: "tp-tab-count" }, String(count)),
      ),
    );
  }
  return wrap;
};

const renderListbar = (visible, pf) => {
  const fresh = state.fetched_at[pf.key];
  return h(
    "div",
    { class: "tp-listbar" },
    h(
      "span",
      { class: "tp-items" },
      h("span", { class: "pf-dot", style: { background: HUE[pf.hue] } }),
      state.query
        ? `${visible.length} résultat${visible.length > 1 ? "s" : ""}`
        : `${visible.length} items`,
    ),
    h(
      "span",
      { class: "tp-upd" },
      h("span", { class: "live-dot" }),
      `Mis à jour ${fmtAgo(fresh)}`,
    ),
  );
};

const renderRow = (item, rank, hue) => {
  const c = heatColor(item.score);
  const scoreTxt =
    Number.isInteger(item.score) ? String(item.score) : item.score.toFixed(1);
  const tag = item.url ? "a" : "div";
  const linkAttrs = item.url
    ? { href: item.url, target: "_blank", rel: "noopener noreferrer" }
    : {};
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
      h("span", { class: "tp-sp-den" }, "/ 100"),
    ),
    h(
      "div",
      { class: "tp-row-mid" },
      h("div", { class: "tp-row-title" }, item.title),
      h(
        "div",
        { class: "tp-row-meta" },
        h(
          "span",
          { class: "tp-pub", style: { "--pub-c": HUE[hue] } },
          item.pub || "—",
        ),
        ...(item.tags && item.tags.length
          ? item.tags.flatMap((t, i) => [
              h("span", { class: "tp-metasep" }, "·"),
              h("span", { class: "tp-tag" }, t),
            ])
          : []),
      ),
    ),
    h(
      "div",
      { class: "tp-row-right" },
      item.metric ? h("span", { class: "tp-metric-chip" }, item.metric) : null,
      item.url
        ? h("span", { class: "tp-ext" }, Ic.link())
        : null,
    ),
  );
};

const renderList = (visible, pf) => {
  if (visible.length === 0) return null;
  const wrap = h("div", { class: "tp-list" });
  visible.slice(0, 100).forEach((it, i) => {
    wrap.appendChild(renderRow(it, i + 1, pf.hue));
  });
  return wrap;
};

const renderEmpty = (pf) => {
  const G = SRC_GLYPH[pf.glyph];
  return h(
    "div",
    { class: "tp-empty" },
    h(
      "div",
      { class: "tp-empty-card" },
      h("div", { class: "tp-empty-ic" }, G ? G() : null),
      h(
        "h3",
        {},
        state.query
          ? "Aucun résultat"
          : `Aucun signal sur ${pf.label} aujourd'hui`,
      ),
      state.query
        ? h(
            "p",
            {},
            `Aucun item ne correspond à « ${state.query} » sur ${pf.label}. `,
            h(
              "button",
              { class: "clearfilter", onClick: () => setState({ query: "" }) },
              "Effacer le filtre",
            ),
          )
        : h(
            "p",
            {},
            "Le connecteur est actif mais n'a rien remonté sur ce support pour la fenêtre en cours. Les items réapparaîtront au prochain passage du pipeline.",
          ),
    ),
  );
};

/* ---------- filtrage + render principal ---------- */

const norm = (s) =>
  (s || "")
    .toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

const filterItems = (items) => {
  if (!state.query) return items;
  const q = norm(state.query);
  return items.filter((it) => {
    const hay = norm(
      `${it.title} ${it.pub || ""} ${(it.tags || []).join(" ")} ${it.metric || ""}`,
    );
    return hay.includes(q);
  });
};

const render = () => {
  const root = document.getElementById("tp-root");
  if (!root) return;
  root.innerHTML = "";

  root.appendChild(renderHero());
  root.appendChild(renderFilterbar());
  root.appendChild(renderTabs());

  const pf = PLATFORMS.find((p) => p.key === state.active);
  const items = state.items[pf.key] || [];
  const visible = filterItems(items);

  root.appendChild(renderListbar(visible, pf));

  if (visible.length === 0) {
    root.appendChild(renderEmpty(pf));
  } else {
    root.appendChild(renderList(visible, pf));
  }
};

/* ---------- mount ---------- */
const mount = async () => {
  render(); // squelette initial
  await loadAll();
  render();

  // raccourci '/' focus l'input recherche
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
