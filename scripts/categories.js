/* ===================================================================
   Tendances par catégorie — vue cross-source par grande thématique.

   Chaque catégorie agrège les items des 8 sources qui matchent la
   thématique selon des règles par source. Le rédac chef voit ainsi
   "ce qui buzze en Sport aujourd'hui sur toutes les plateformes" en
   un coup d'œil.
   =================================================================== */

/* ----- Catégories canoniques (inspirées Google News + adaptées) ----- */

const CATEGORIES = [
  { key: "politique", label: "Politique", emoji: "🏛" },
  { key: "international", label: "International", emoji: "🌍" },
  { key: "economie", label: "Économie", emoji: "📈" },
  { key: "tech", label: "Tech & Numérique", emoji: "💻" },
  { key: "sport", label: "Sport", emoji: "⚽️" },
  { key: "people", label: "Divertissement & People", emoji: "🎬" },
  { key: "science", label: "Science", emoji: "🔬" },
  { key: "sante", label: "Santé", emoji: "❤️" },
  { key: "societe", label: "Société", emoji: "🤝" },
  { key: "lifestyle", label: "Lifestyle", emoji: "🌿" },
];

/* ----- Classifieur item -> catégorie -----
   Retourne la clé d'une catégorie, ou null si non classifié.
   On évalue dans un ordre prioritaire (du plus spécifique au plus large)
   pour qu'un article /News/Politics soit Politique et pas Société. */

const norm = (s) =>
  (s || "").toString().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

const startsWithAny = (s, prefixes) => {
  const lc = (s || "").toLowerCase();
  return prefixes.some((p) => lc.startsWith(p.toLowerCase()));
};

/** Classifie un article Discoversnoop par sa `category` (taxonomie Google). */
const classifyDiscover = (item) => {
  const c = item.category || "";
  // Sous-catégories /News d'abord (plus spécifique)
  if (c.startsWith("/News/Politics")) return "politique";
  if (c.startsWith("/News/World News")) return "international";
  if (c.startsWith("/News/Business News")) return "economie";
  if (c.startsWith("/News/Sports News")) return "sport";
  if (c.startsWith("/News/Local")) return "societe";
  if (c.startsWith("/News/Weather")) return "societe";
  // Top-level
  if (c.startsWith("/Law & Government")) return "politique";
  if (c.startsWith("/Sports")) return "sport";
  if (c.startsWith("/Arts & Entertainment")) return "people";
  if (c.startsWith("/Health")) return "sante";
  if (c.startsWith("/Beauty & Fitness")) return "sante";
  if (c.startsWith("/Science")) return "science";
  if (c.startsWith("/Computers & Electronics")) return "tech";
  if (c.startsWith("/Internet & Telecom")) return "tech";
  if (c.startsWith("/Finance")) return "economie";
  if (c.startsWith("/Business & Industrial")) return "economie";
  if (c.startsWith("/Food & Drink")) return "lifestyle";
  if (c.startsWith("/Travel")) return "lifestyle";
  if (c.startsWith("/Home & Garden")) return "lifestyle";
  if (c.startsWith("/Autos & Vehicles")) return "lifestyle";
  if (c.startsWith("/Pets & Animals")) return "lifestyle";
  if (c.startsWith("/Hobbies & Leisure")) return "lifestyle";
  if (c.startsWith("/People & Society")) return "societe";
  if (c.startsWith("/Sensitive Subjects")) return "societe";
  if (c.startsWith("/News")) return "societe"; // generic news fallback
  return null;
};

/** GNews : la `category` est définie par notre mapping FEEDS (cf google_news.py). */
const classifyGnews = (item) => {
  const c = (item.category || "").toLowerCase();
  const map = {
    politique: "politique",
    international: "international",
    economie: "economie",
    technologie: "tech",
    sports: "sport",
    divertissement: "people",
    science: "science",
    sante: "sante",
    france: "societe", // flux général France
    general: null, // fourre-tout
  };
  return map[c] ?? null;
};

/** MSN : `category` éditoriale propre à MSN. */
const classifyMsn = (item) => {
  const c = (item.category || "").toLowerCase();
  if (c.includes("politique")) return "politique";
  if (c.includes("sport")) return "sport";
  if (c.includes("divertissement")) return "people";
  if (c.includes("lifestyle") || c.includes("style")) return "lifestyle";
  if (c.includes("finance") || c.includes("eco")) return "economie";
  if (c.includes("tech") || c.includes("numer")) return "tech";
  if (c.includes("sante") || c.includes("sante")) return "sante";
  if (c.includes("sciences")) return "science";
  if (c.includes("monde") || c.includes("inter")) return "international";
  if (c === "actualite") return "societe";
  return null;
};

/** Reddit : mapping subreddit -> catégorie. */
const REDDIT_SUB_MAP = {
  france: "societe",
  actualite: "societe",
  AskFrance: "societe",
  francepolitique: "politique",
  Politique: "politique",
  europe: "international",
  sciences: "science",
  Histoire: "science", // proche assez
  technologie: "tech",
  jeuxvideo: "people",
  cinema_francais: "people",
  musique: "people",
  musiquefrancaise: "people",
  Cuisine: "lifestyle",
  cuisine: "lifestyle",
  sport_FR: "sport",
};

const classifyReddit = (item) => {
  return REDDIT_SUB_MAP[item.subreddit] || null;
};

/** YouTube : mapping category_label -> catégorie. */
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

const classifyYoutube = (item) => {
  return YOUTUBE_CAT_MAP[item.category_label] || null;
};

/** Google Trends : champ `categories` (array). */
const classifyTrends = (item) => {
  const cats = (item.categories || []).map(norm);
  if (cats.some((c) => c.includes("politi"))) return "politique";
  if (cats.some((c) => c.includes("sport"))) return "sport";
  if (cats.some((c) => c.includes("divertis") || c.includes("celebrit")))
    return "people";
  if (cats.some((c) => c.includes("technolog") || c.includes("internet")))
    return "tech";
  if (cats.some((c) => c.includes("science"))) return "science";
  if (cats.some((c) => c.includes("sante"))) return "sante";
  if (cats.some((c) => c.includes("commerc") || c.includes("financ")))
    return "economie";
  if (cats.some((c) => c.includes("voyage") || c.includes("alimen") || c.includes("auto")))
    return "lifestyle";
  return null;
};

/* ----- Source loaders + descripteurs ----- */

const SOURCES = [
  {
    key: "discover",
    file: "discoversnoop",
    label: "Discover",
    itemsKey: "articles",
    classify: classifyDiscover,
  },
  {
    key: "gnews",
    file: "google_news",
    label: "Google News",
    itemsKey: "articles",
    classify: classifyGnews,
  },
  {
    key: "reddit",
    file: "reddit",
    label: "Reddit",
    itemsKey: "posts",
    classify: classifyReddit,
  },
  {
    key: "youtube",
    file: "youtube_trending",
    label: "YouTube",
    itemsKey: "videos",
    classify: classifyYoutube,
  },
  {
    key: "trends",
    file: "google_trends",
    label: "Google Trends",
    itemsKey: null, // structure différente (windows.current.trends)
    classify: classifyTrends,
  },
  {
    key: "msn",
    file: "msn",
    label: "MSN",
    itemsKey: "articles",
    classify: classifyMsn,
  },
];

const state = {
  raw: {}, // { sourceKey: parsedJson }
  classified: {}, // { categoryKey: { sourceKey: [items] } }
  active: "politique",
  query: "",
};

/* ----- Helpers DOM ----- */

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

const fmtVolume = (n, suffix = "") => {
  const v = Number(n) || 0;
  if (!v) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M${suffix}`;
  if (v >= 1_000) return `${Math.round(v / 1_000)}k${suffix}`;
  return `${v}${suffix}`;
};

const fmtRelativeTime = (iso) => {
  if (!iso) return "";
  try {
    const dt = new Date(iso);
    const minutes = Math.floor((Date.now() - dt.getTime()) / 60000);
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} h`;
    return `${Math.floor(hours / 24)} j`;
  } catch {
    return "";
  }
};

/* ----- Chargement + classification ----- */

const loadAll = async () => {
  const results = await Promise.all(
    SOURCES.map(async (s) => {
      try {
        const r = await fetch(`data/${s.file}/latest.json`, { cache: "no-store" });
        if (!r.ok) return [s.key, null];
        return [s.key, await r.json()];
      } catch {
        return [s.key, null];
      }
    }),
  );
  state.raw = Object.fromEntries(results);
  classifyAll();
};

const classifyAll = () => {
  // Init buckets
  const buckets = {};
  for (const cat of CATEGORIES) {
    buckets[cat.key] = {};
    for (const s of SOURCES) buckets[cat.key][s.key] = [];
  }

  for (const s of SOURCES) {
    const data = state.raw[s.key];
    if (!data) continue;

    let items = [];
    if (s.key === "trends") {
      items = ((data.windows && data.windows.current) || {}).trends || [];
    } else if (s.itemsKey) {
      items = data[s.itemsKey] || [];
    }

    for (const item of items) {
      const cat = s.classify(item);
      if (cat && buckets[cat]) {
        buckets[cat][s.key].push(item);
      }
    }
  }
  state.classified = buckets;
};

/* ----- Filtre par recherche ----- */

const matchesQuery = (item, sourceKey) => {
  if (!state.query) return true;
  const q = state.query;
  let hay = "";
  switch (sourceKey) {
    case "discover":
      hay = `${item.title || ""} ${item.publisher || ""} ${item.category || ""}`;
      break;
    case "gnews":
      hay = `${item.title || ""} ${item.source || ""}`;
      break;
    case "reddit":
      hay = `${item.title || ""} ${item.subreddit || ""}`;
      break;
    case "youtube":
      hay = `${item.title || ""} ${item.channel || ""} ${item.description || ""}`;
      break;
    case "trends":
      hay = `${item.query || ""}`;
      break;
    case "msn":
      hay = `${item.title || ""} ${item.source || ""}`;
      break;
  }
  return norm(hay).includes(q);
};

/* ----- Renderers compacts par source dans la catégorie active ----- */

const renderDiscoverItem = (item) => {
  const score = Number(item.score) || 0;
  const scoreDisplay =
    score >= 10 ? score.toFixed(0) : score >= 1 ? score.toFixed(1) : "—";
  return h(
    "li",
    { class: "cat-item" },
    h(
      "div",
      { class: "cat-item__metric", "data-source-color": "discover" },
      h("span", { class: "cat-item__metric-value" }, scoreDisplay),
      h("span", { class: "cat-item__metric-unit" }, "/65"),
    ),
    h(
      "div",
      { class: "cat-item__body" },
      item.url
        ? h(
            "a",
            { class: "cat-item__title", href: item.url, target: "_blank", rel: "noopener noreferrer" },
            item.title || "(sans titre)",
          )
        : h("span", { class: "cat-item__title" }, item.title || "(sans titre)"),
      h(
        "div",
        { class: "cat-item__meta" },
        item.publisher ? h("span", { class: "cat-item__publisher" }, item.publisher) : null,
      ),
    ),
  );
};

const renderGnewsItem = (item) => {
  return h(
    "li",
    { class: "cat-item" },
    h(
      "div",
      { class: "cat-item__metric", "data-source-color": "gnews" },
      h("span", { class: "cat-item__metric-value" }, "GN"),
    ),
    h(
      "div",
      { class: "cat-item__body" },
      h(
        "a",
        { class: "cat-item__title", href: item.url, target: "_blank", rel: "noopener noreferrer" },
        item.title,
      ),
      h(
        "div",
        { class: "cat-item__meta" },
        item.source ? h("span", { class: "cat-item__publisher" }, item.source) : null,
        item.published_at
          ? h("span", { class: "cat-item__time" }, fmtRelativeTime(item.published_at))
          : null,
      ),
    ),
  );
};

const renderRedditItem = (item) => {
  const url = item.url || item.permalink;
  return h(
    "li",
    { class: "cat-item" },
    h(
      "div",
      { class: "cat-item__metric", "data-source-color": "reddit" },
      h("span", { class: "cat-item__metric-value" }, `×${item.cross_subs_count || 1}`),
    ),
    h(
      "div",
      { class: "cat-item__body" },
      url
        ? h(
            "a",
            { class: "cat-item__title", href: url, target: "_blank", rel: "noopener noreferrer" },
            item.title,
          )
        : h("span", { class: "cat-item__title" }, item.title),
      h(
        "div",
        { class: "cat-item__meta" },
        h("span", { class: "cat-item__publisher" }, `r/${item.subreddit}`),
      ),
    ),
  );
};

const renderYoutubeItem = (item) => {
  return h(
    "li",
    { class: "cat-item cat-item--video" },
    item.thumbnail
      ? h("img", {
          class: "cat-item__thumb",
          src: item.thumbnail,
          alt: "",
          loading: "lazy",
          width: 90,
          height: 50,
        })
      : null,
    h(
      "div",
      { class: "cat-item__metric", "data-source-color": "youtube" },
      h(
        "span",
        { class: "cat-item__metric-value" },
        fmtVolume(item.velocity_views_per_hour),
      ),
      h("span", { class: "cat-item__metric-unit" }, "/h"),
    ),
    h(
      "div",
      { class: "cat-item__body" },
      h(
        "a",
        { class: "cat-item__title", href: item.url, target: "_blank", rel: "noopener noreferrer" },
        item.title,
      ),
      h(
        "div",
        { class: "cat-item__meta" },
        h("span", { class: "cat-item__publisher" }, item.channel || "—"),
      ),
    ),
  );
};

const renderTrendsItem = (item) => {
  return h(
    "li",
    { class: "cat-item" },
    h(
      "div",
      { class: "cat-item__metric", "data-source-color": "trends" },
      h("span", { class: "cat-item__metric-value" }, fmtVolume(item.search_volume)),
      h("span", { class: "cat-item__metric-unit" }, "rech."),
    ),
    h(
      "div",
      { class: "cat-item__body" },
      h("span", { class: "cat-item__title" }, item.query || "—"),
      item.percentage_increase
        ? h(
            "div",
            { class: "cat-item__meta" },
            h("span", { class: "cat-item__publisher" }, `+${item.percentage_increase}%`),
          )
        : null,
    ),
  );
};

const renderMsnItem = (item) => {
  const engagement = (item.upvotes || 0) + (item.comments || 0);
  return h(
    "li",
    { class: "cat-item" },
    h(
      "div",
      { class: "cat-item__metric", "data-source-color": "msn" },
      h(
        "span",
        { class: "cat-item__metric-value" },
        engagement > 0 ? `${engagement}` : "—",
      ),
      h("span", { class: "cat-item__metric-unit" }, "réact."),
    ),
    h(
      "div",
      { class: "cat-item__body" },
      item.url
        ? h(
            "a",
            { class: "cat-item__title", href: item.url, target: "_blank", rel: "noopener noreferrer" },
            item.title,
          )
        : h("span", { class: "cat-item__title" }, item.title),
      h(
        "div",
        { class: "cat-item__meta" },
        item.source ? h("span", { class: "cat-item__publisher" }, item.source) : null,
      ),
    ),
  );
};

const RENDERERS = {
  discover: renderDiscoverItem,
  gnews: renderGnewsItem,
  reddit: renderRedditItem,
  youtube: renderYoutubeItem,
  trends: renderTrendsItem,
  msn: renderMsnItem,
};

const SORT_KEYS = {
  discover: (a, b) => (Number(b.score) || 0) - (Number(a.score) || 0),
  msn: (a, b) =>
    ((b.upvotes || 0) + (b.comments || 0) * 2) -
    ((a.upvotes || 0) + (a.comments || 0) * 2),
  youtube: (a, b) =>
    (b.velocity_views_per_hour || 0) - (a.velocity_views_per_hour || 0),
  reddit: (a, b) =>
    (b.cross_subs_count || 0) - (a.cross_subs_count || 0) ||
    (a.best_rank || 99) - (b.best_rank || 99),
  trends: (a, b) => (b.search_volume || 0) - (a.search_volume || 0),
  gnews: () => 0, // ordre du flux RSS
};

/* ----- Renderer principal d'une catégorie ----- */

const renderCategory = (catKey) => {
  const cat = CATEGORIES.find((c) => c.key === catKey);
  const buckets = state.classified[catKey] || {};

  // Compteurs cross-source (avec filtre query si actif)
  const sectionsWithItems = SOURCES.filter((s) => {
    const items = (buckets[s.key] || []).filter((it) =>
      matchesQuery(it, s.key),
    );
    return items.length > 0;
  });

  const totalItems = sectionsWithItems.reduce(
    (sum, s) =>
      sum + (buckets[s.key] || []).filter((it) => matchesQuery(it, s.key)).length,
    0,
  );

  if (totalItems === 0) {
    return h(
      "div",
      { class: "source-panel__empty" },
      h(
        "strong",
        {},
        state.query
          ? `Aucun match pour "${state.query}" en ${cat.label}`
          : `Aucun item en ${cat.label} aujourd'hui`,
      ),
      h(
        "p",
        {},
        state.query
          ? "Essaie une autre catégorie ou efface la recherche."
          : "Les snapshots actuels ne contiennent rien dans cette catégorie — réessaie après le prochain run du pipeline (toutes les 6h).",
      ),
    );
  }

  const container = h("div", { class: "cat-sections" });

  // Méta header
  container.appendChild(
    h(
      "p",
      { class: "cat-summary" },
      h(
        "span",
        { class: "cat-summary__total" },
        `${totalItems} items dans ${cat.label}`,
      ),
      h(
        "span",
        { class: "cat-summary__breakdown" },
        sectionsWithItems
          .map((s) => {
            const n = (buckets[s.key] || []).filter((it) =>
              matchesQuery(it, s.key),
            ).length;
            return `${s.label} (${n})`;
          })
          .join(" · "),
      ),
    ),
  );

  // Une section par source qui contient des items
  for (const s of sectionsWithItems) {
    const allItems = buckets[s.key] || [];
    const filtered = allItems.filter((it) => matchesQuery(it, s.key));
    const sorter = SORT_KEYS[s.key];
    const sorted = sorter ? [...filtered].sort(sorter) : filtered;
    const displayed = sorted.slice(0, 20);
    const renderer = RENDERERS[s.key];

    container.appendChild(
      h(
        "section",
        { class: "cat-section" },
        h(
          "header",
          { class: "cat-section__header", "data-source-color": s.key },
          h("span", { class: "cat-section__dot", "data-source-color": s.key }),
          h("h2", { class: "cat-section__title" }, s.label),
          h(
            "span",
            { class: "cat-section__count" },
            `${displayed.length}${filtered.length > displayed.length ? `/${filtered.length}` : ""}`,
          ),
        ),
        h(
          "ul",
          { class: "cat-section__list" },
          displayed.map((item) => renderer(item)),
        ),
      ),
    );
  }

  return container;
};

/* ----- Onglets ----- */

const renderTabs = () => {
  const nav = document.querySelector("#cat-tabs");
  nav.innerHTML = "";
  for (const cat of CATEGORIES) {
    const count = computeCategoryCount(cat.key);
    const btn = h(
      "button",
      {
        class: "cat-tab" + (cat.key === state.active ? " is-active" : ""),
        role: "tab",
        "data-cat": cat.key,
        "aria-selected": cat.key === state.active ? "true" : "false",
        onClick: () => showCategory(cat.key),
      },
      h("span", { class: "cat-tab__emoji" }, cat.emoji),
      h("span", { class: "cat-tab__name" }, cat.label),
      h("span", { class: "cat-tab__count" }, count > 0 ? String(count) : "—"),
    );
    nav.appendChild(btn);
  }
};

const computeCategoryCount = (catKey) => {
  const buckets = state.classified[catKey] || {};
  return SOURCES.reduce((sum, s) => {
    const items = (buckets[s.key] || []).filter((it) =>
      matchesQuery(it, s.key),
    );
    return sum + items.length;
  }, 0);
};

const refreshTabCounts = () => {
  document.querySelectorAll(".cat-tab").forEach((btn) => {
    const catKey = btn.dataset.cat;
    const count = computeCategoryCount(catKey);
    const node = btn.querySelector(".cat-tab__count");
    if (node) node.textContent = count > 0 ? String(count) : "—";
  });
};

const showCategory = (catKey) => {
  state.active = catKey;
  document.querySelectorAll(".cat-tab").forEach((t) => {
    const active = t.dataset.cat === catKey;
    t.classList.toggle("is-active", active);
    t.setAttribute("aria-selected", active ? "true" : "false");
  });
  const panel = document.querySelector("#cat-panel");
  panel.innerHTML = "";
  panel.appendChild(renderCategory(catKey));
};

/* ----- Recherche ----- */

let _searchDebounce = null;
const wireSearch = () => {
  const input = document.querySelector("#cat-search");
  const clear = document.querySelector("#cat-search-clear");
  if (!input) return;

  const apply = () => {
    state.query = norm(input.value.trim());
    clear.hidden = !input.value;
    refreshTabCounts();
    showCategory(state.active);
  };

  input.addEventListener("input", () => {
    clearTimeout(_searchDebounce);
    _searchDebounce = setTimeout(apply, 200);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && input.value) {
      input.value = "";
      apply();
    }
  });

  clear.addEventListener("click", () => {
    input.value = "";
    apply();
    input.focus();
  });
};

/* ----- Mount ----- */

const mount = async () => {
  await loadAll();
  renderTabs();
  wireSearch();
  // Choisit la catégorie la mieux dotée par défaut (= la plus animée)
  let bestCat = "politique";
  let bestCount = -1;
  for (const cat of CATEGORIES) {
    const n = computeCategoryCount(cat.key);
    if (n > bestCount) {
      bestCount = n;
      bestCat = cat.key;
    }
  }
  showCategory(bestCat);
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
