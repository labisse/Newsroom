/* ===================================================================
   Tendances par source — vue brute, signal par signal.

   Chaque onglet charge data/{source}/latest.json et rend une liste
   adaptée au format de la source (titre, publisher, métrique iconique,
   lien). Pas de scoring agrégé ici — c'est la vue analytique brute.
   =================================================================== */

const SOURCES = [
  { key: "discover", file: "discoversnoop", label: "Discover" },
  { key: "gnews", file: "google_news", label: "Google News" },
  { key: "reddit", file: "reddit", label: "Reddit" },
  { key: "youtube", file: "youtube_trending", label: "YouTube" },
  { key: "trends", file: "google_trends", label: "Google Trends" },
  { key: "wiki", file: "wikimedia", label: "Wikipedia" },
  { key: "x", file: "x_trends", label: "X" },
  { key: "msn", file: "msn", label: "MSN" },
];

const state = {
  data: {}, // { sourceKey: parsedJson }
  active: "discover",
  query: "", // normalisé (lowercase + sans accents)
};

/* Normalise une string pour la recherche (lowercase + sans diacritiques).
   "École Élysée" → "ecole elysee" */
const normalize = (s) =>
  (s || "")
    .toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

/**
 * Détermine si un item matche la query selon le type de source.
 * On cherche dans le titre + champs secondaires utiles à l'éditorial
 * (publisher, channel, subreddit, category…).
 */
const matchesQuery = (item, sourceKey, q) => {
  if (!q) return true;
  const haystack = [];
  switch (sourceKey) {
    case "discover":
      haystack.push(item.title, item.publisher, item.category);
      break;
    case "gnews":
      haystack.push(item.title, item.source, item.category);
      break;
    case "reddit":
      haystack.push(item.title, item.subreddit, item.domain);
      if (Array.isArray(item.cross_subs))
        haystack.push(item.cross_subs.join(" "));
      break;
    case "youtube":
      haystack.push(
        item.title,
        item.channel,
        item.category_label,
        item.description,
      );
      if (Array.isArray(item.tags)) haystack.push(item.tags.join(" "));
      break;
    case "trends":
      haystack.push(item.query);
      if (Array.isArray(item.categories))
        haystack.push(item.categories.join(" "));
      break;
    case "wiki":
      haystack.push(item.title_display, item.article);
      break;
    case "x":
      haystack.push(item.query, item.name);
      break;
    case "msn":
      haystack.push(item.title, item.source, item.category);
      break;
    default:
      haystack.push(item.title);
  }
  const hay = normalize(haystack.filter(Boolean).join("   "));
  return hay.includes(q);
};

/** Filtre une liste d'items selon la query active. */
const filterItems = (items, sourceKey) =>
  state.query
    ? items.filter((i) => matchesQuery(i, sourceKey, state.query))
    : items;

/** Items "bruts" d'une source (avant tri/filtre) — pour les compteurs. */
const rawItemsFor = (sourceKey, data) => {
  if (!data || data.__error) return [];
  switch (sourceKey) {
    case "discover":
    case "gnews":
    case "wiki":
    case "msn":
      return data.articles || [];
    case "reddit":
      return data.posts || [];
    case "youtube":
      return data.videos || [];
    case "trends":
      return ((data.windows && data.windows.current) || {}).trends || [];
    case "x":
      return data.trends || [];
    default:
      return [];
  }
};

/* ----- Helpers ----- */

const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, String(v));
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

const truncate = (s, n = 120) =>
  s && s.length > n ? s.slice(0, n - 1) + "…" : s || "";

const fmtRelativeTime = (iso) => {
  if (!iso) return "";
  try {
    const dt = new Date(iso);
    const minutes = Math.floor((Date.now() - dt.getTime()) / 60000);
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} h`;
    const days = Math.floor(hours / 24);
    return `${days} j`;
  } catch {
    return "";
  }
};

/* ----- Chargement ----- */

const loadSource = async (sourceKey) => {
  if (state.data[sourceKey]) return state.data[sourceKey];
  const meta = SOURCES.find((s) => s.key === sourceKey);
  if (!meta) return null;
  try {
    const response = await fetch(`data/${meta.file}/latest.json`, {
      cache: "no-store",
    });
    if (!response.ok) {
      state.data[sourceKey] = { __error: `HTTP ${response.status}` };
      return state.data[sourceKey];
    }
    state.data[sourceKey] = await response.json();
    return state.data[sourceKey];
  } catch (err) {
    state.data[sourceKey] = { __error: err.message || "Erreur de chargement" };
    return state.data[sourceKey];
  }
};

const updateCounts = async () => {
  // Charge tous les snapshots en parallèle puis compte (avec ou sans filtre)
  await Promise.all(
    SOURCES.map(async (s) => {
      const data = await loadSource(s.key);
      const count = countFor(s.key, data);
      const node = document.querySelector(`[data-count="${s.key}"]`);
      if (node) node.textContent = count != null ? `${count}` : "—";
    }),
  );
};

/** Recompte les items par source — synchrone, utilise le cache state.data.
 *  Appelé pendant la frappe de l'utilisateur pour MAJ les onglets. */
const recomputeCounts = () => {
  for (const s of SOURCES) {
    const data = state.data[s.key];
    const count = countFor(s.key, data);
    const node = document.querySelector(`[data-count="${s.key}"]`);
    if (node) node.textContent = count != null ? `${count}` : "—";
  }
};

const countFor = (sourceKey, data) => {
  if (!data || data.__error) return null;
  const raw = rawItemsFor(sourceKey, data);
  return filterItems(raw, sourceKey).length;
};

/* ----- Renderers par source ----- */

const renderError = (msg) =>
  h(
    "div",
    { class: "source-panel__empty" },
    h("strong", {}, "Snapshot indisponible"),
    h("p", {}, msg),
  );

const renderMeta = (data, sourceKey) => {
  const fetched = data.fetched_at ? fmtRelativeTime(data.fetched_at) : "?";
  const count = countFor(sourceKey, data);
  return h(
    "p",
    { class: "source-panel__meta" },
    h(
      "span",
      { class: "source-panel__meta-pill", "data-source-color": sourceKey },
      `${count != null ? count : "—"} items`,
    ),
    h(
      "span",
      { class: "source-panel__meta-time" },
      `Mis à jour il y a ${fetched}`,
    ),
  );
};

const renderDiscover = (data) => {
  const articles = filterItems(
    [...(data.articles || [])].sort(
      (a, b) => (Number(b.score) || 0) - (Number(a.score) || 0),
    ),
    "discover",
  ).slice(0, 50);
  return h(
    "div",
    {},
    renderMeta(data, "discover"),
    h(
      "ul",
      { class: "source-list" },
      articles.map((a, i) => {
        const score = Number(a.score) || 0;
        const scoreDisplay =
          score >= 10 ? score.toFixed(0) : score >= 1 ? score.toFixed(1) : "—";
        return h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "discover" },
            h("span", { class: "source-row__metric-value" }, scoreDisplay),
            h("span", { class: "source-row__metric-unit" }, "/65"),
          ),
          h(
            "div",
            { class: "source-row__body" },
            a.url
              ? h(
                  "a",
                  {
                    class: "source-row__title",
                    href: a.url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                  },
                  a.title || "(sans titre)",
                )
              : h("span", { class: "source-row__title" }, a.title || "(sans titre)"),
            h(
              "div",
              { class: "source-row__meta" },
              a.publisher
                ? h("span", { class: "source-row__publisher" }, a.publisher)
                : null,
              a.category
                ? h(
                    "span",
                    { class: "source-row__category" },
                    a.category.split("/").filter(Boolean).slice(-2).join(" · "),
                  )
                : null,
            ),
          ),
        );
      }),
    ),
  );
};

const renderGnews = (data) => {
  const articles = filterItems(data.articles || [], "gnews").slice(0, 50);
  return h(
    "div",
    {},
    renderMeta(data, "gnews"),
    h(
      "ul",
      { class: "source-list" },
      articles.map((a, i) =>
        h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "gnews" },
            h("span", { class: "source-row__metric-label" }, a.category || "actu"),
          ),
          h(
            "div",
            { class: "source-row__body" },
            h(
              "a",
              {
                class: "source-row__title",
                href: a.url,
                target: "_blank",
                rel: "noopener noreferrer",
              },
              a.title,
            ),
            h(
              "div",
              { class: "source-row__meta" },
              a.source
                ? h("span", { class: "source-row__publisher" }, a.source)
                : null,
              a.published_at
                ? h(
                    "span",
                    { class: "source-row__category" },
                    fmtRelativeTime(a.published_at),
                  )
                : null,
            ),
          ),
        ),
      ),
    ),
  );
};

const renderReddit = (data) => {
  const posts = filterItems(data.posts || [], "reddit").slice(0, 50);
  return h(
    "div",
    {},
    renderMeta(data, "reddit"),
    h(
      "ul",
      { class: "source-list" },
      posts.map((p, i) => {
        const url = p.url || p.permalink;
        return h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "reddit" },
            h(
              "span",
              { class: "source-row__metric-value" },
              `×${p.cross_subs_count || 1}`,
            ),
            h("span", { class: "source-row__metric-unit" }, "subs"),
          ),
          h(
            "div",
            { class: "source-row__body" },
            url
              ? h(
                  "a",
                  {
                    class: "source-row__title",
                    href: url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                  },
                  p.title,
                )
              : h("span", { class: "source-row__title" }, p.title),
            h(
              "div",
              { class: "source-row__meta" },
              h("span", { class: "source-row__publisher" }, `r/${p.subreddit}`),
              p.cross_subs && p.cross_subs.length > 1
                ? h(
                    "span",
                    { class: "source-row__category" },
                    `aussi sur ${p.cross_subs.filter((s) => s !== p.subreddit).slice(0, 3).map((s) => "r/" + s).join(", ")}`,
                  )
                : p.domain
                  ? h("span", { class: "source-row__category" }, p.domain)
                  : null,
            ),
          ),
        );
      }),
    ),
  );
};

const renderYoutube = (data) => {
  const videos = filterItems(data.videos || [], "youtube").slice(0, 50);
  if (videos.length === 0 && (data.failures || []).length) {
    return h(
      "div",
      {},
      renderMeta(data, "youtube"),
      renderError(
        data.failures[0].reason === "missing_api_key"
          ? "Clé API YouTube manquante (YOUTUBE_API_KEY)"
          : data.failures[0].error || "Erreur API",
      ),
    );
  }
  return h(
    "div",
    {},
    renderMeta(data, "youtube"),
    h(
      "ul",
      { class: "source-list source-list--with-thumb" },
      videos.map((v, i) =>
        h(
          "li",
          { class: "source-row source-row--video" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          v.thumbnail
            ? h("img", {
                class: "source-row__thumb",
                src: v.thumbnail,
                alt: "",
                loading: "lazy",
                width: 120,
                height: 68,
              })
            : null,
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "youtube" },
            h(
              "span",
              { class: "source-row__metric-value" },
              fmtVolume(v.velocity_views_per_hour),
            ),
            h("span", { class: "source-row__metric-unit" }, "/h"),
          ),
          h(
            "div",
            { class: "source-row__body" },
            h(
              "a",
              {
                class: "source-row__title",
                href: v.url,
                target: "_blank",
                rel: "noopener noreferrer",
              },
              v.title,
            ),
            h(
              "div",
              { class: "source-row__meta" },
              h("span", { class: "source-row__publisher" }, v.channel || "—"),
              h(
                "span",
                { class: "source-row__category" },
                `${v.category_label || ""} · ${fmtVolume(v.views, " vues")}`,
              ),
            ),
          ),
        ),
      ),
    ),
  );
};

const renderTrends = (data) => {
  const w = (data.windows && data.windows.current) || {};
  const trends = filterItems(w.trends || [], "trends").slice(0, 50);
  return h(
    "div",
    {},
    renderMeta(data, "trends"),
    h(
      "ul",
      { class: "source-list" },
      trends.map((t, i) =>
        h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "trends" },
            h(
              "span",
              { class: "source-row__metric-value" },
              fmtVolume(t.search_volume),
            ),
            h("span", { class: "source-row__metric-unit" }, "rech."),
          ),
          h(
            "div",
            { class: "source-row__body" },
            h("span", { class: "source-row__title" }, t.query || "—"),
            h(
              "div",
              { class: "source-row__meta" },
              t.percentage_increase
                ? h(
                    "span",
                    { class: "source-row__publisher" },
                    `+${t.percentage_increase}%`,
                  )
                : null,
              t.categories && t.categories.length
                ? h(
                    "span",
                    { class: "source-row__category" },
                    t.categories.slice(0, 2).join(", "),
                  )
                : null,
            ),
          ),
        ),
      ),
    ),
  );
};

const renderWiki = (data) => {
  const articles = filterItems(data.articles || [], "wiki").slice(0, 50);
  const project = data.project || "fr.wikipedia";
  // L'URL d'un article Wikipedia se construit depuis le slug `article`
  // (fields snapshotés par wikimedia.py). Project domain = fr.wikipedia.org
  const projectDomain = project.includes(".")
    ? `${project.split(".")[0]}.wikipedia.org`
    : "fr.wikipedia.org";
  return h(
    "div",
    {},
    renderMeta(data, "wiki"),
    h(
      "ul",
      { class: "source-list" },
      articles.map((a, i) => {
        const url = a.article
          ? `https://${projectDomain}/wiki/${a.article}`
          : "";
        const title = a.title_display || a.article || "—";
        return h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "wiki" },
            h(
              "span",
              { class: "source-row__metric-value" },
              fmtVolume(a.views),
            ),
            h("span", { class: "source-row__metric-unit" }, "vues"),
          ),
          h(
            "div",
            { class: "source-row__body" },
            url
              ? h(
                  "a",
                  {
                    class: "source-row__title",
                    href: url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                  },
                  title,
                )
              : h("span", { class: "source-row__title" }, title),
            h(
              "div",
              { class: "source-row__meta" },
              h("span", { class: "source-row__publisher" }, project),
            ),
          ),
        );
      }),
    ),
  );
};

const renderX = (data) => {
  const trends = filterItems(data.trends || [], "x").slice(0, 50);
  return h(
    "div",
    {},
    renderMeta(data, "x"),
    h(
      "ul",
      { class: "source-list" },
      trends.map((t, i) =>
        h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "x" },
            h("span", { class: "source-row__metric-value" }, `#${i + 1}`),
          ),
          h(
            "div",
            { class: "source-row__body" },
            h("span", { class: "source-row__title" }, t.query || t.name || "—"),
            t.tweet_count
              ? h(
                  "div",
                  { class: "source-row__meta" },
                  h(
                    "span",
                    { class: "source-row__publisher" },
                    fmtVolume(t.tweet_count, " tweets"),
                  ),
                )
              : null,
          ),
        ),
      ),
    ),
  );
};

const renderMsn = (data) => {
  const articles = filterItems(
    [...(data.articles || [])].sort((a, b) => {
      const ae = (a.upvotes || 0) + (a.comments || 0) * 2;
      const be = (b.upvotes || 0) + (b.comments || 0) * 2;
      return be - ae;
    }),
    "msn",
  ).slice(0, 50);
  return h(
    "div",
    {},
    renderMeta(data, "msn"),
    h(
      "ul",
      { class: "source-list" },
      articles.map((a, i) => {
        const engagement = (a.upvotes || 0) + (a.comments || 0);
        return h(
          "li",
          { class: "source-row" },
          h("span", { class: "source-row__rank" }, String(i + 1).padStart(2, "0")),
          h(
            "div",
            { class: "source-row__metric", "data-source-color": "msn" },
            h(
              "span",
              { class: "source-row__metric-value" },
              engagement > 0 ? `${engagement}` : "—",
            ),
            h("span", { class: "source-row__metric-unit" }, "réact."),
          ),
          h(
            "div",
            { class: "source-row__body" },
            a.url
              ? h(
                  "a",
                  {
                    class: "source-row__title",
                    href: a.url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                  },
                  a.title,
                )
              : h("span", { class: "source-row__title" }, a.title),
            h(
              "div",
              { class: "source-row__meta" },
              h("span", { class: "source-row__publisher" }, a.source || "MSN"),
              a.category
                ? h("span", { class: "source-row__category" }, a.category)
                : null,
            ),
          ),
        );
      }),
    ),
  );
};

const RENDERERS = {
  discover: renderDiscover,
  gnews: renderGnews,
  reddit: renderReddit,
  youtube: renderYoutube,
  trends: renderTrends,
  wiki: renderWiki,
  x: renderX,
  msn: renderMsn,
};

const showSource = async (sourceKey) => {
  state.active = sourceKey;

  // Toggle active state on tabs
  document.querySelectorAll(".source-tab").forEach((t) => {
    const isActive = t.dataset.source === sourceKey;
    t.classList.toggle("is-active", isActive);
    t.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  const panel = document.querySelector("#source-panel");
  panel.innerHTML = "";
  panel.appendChild(
    h("div", { class: "source-panel__loading" }, "Chargement…"),
  );

  const data = await loadSource(sourceKey);
  panel.innerHTML = "";

  if (!data || data.__error) {
    panel.appendChild(renderError(data?.__error || "Snapshot indisponible"));
    return;
  }

  const renderer = RENDERERS[sourceKey];
  const rendered = renderer(data);
  panel.appendChild(rendered);

  // Si un filtre est actif mais ne ramène aucun item, complète avec un
  // message d'orientation (le renderer affiche déjà une liste vide).
  const list = panel.querySelector(".source-list");
  if (state.query && list && list.children.length === 0) {
    panel.appendChild(
      h(
        "div",
        { class: "source-panel__empty" },
        h("strong", {}, `Aucun match pour "${state.query}"`),
        h(
          "p",
          {},
          "Essaie un autre mot-clé, change d'onglet (les compteurs ci-dessus indiquent où le terme apparaît), ou efface la recherche.",
        ),
      ),
    );
  }
};

/** Câblage de la barre de recherche : debounce 200ms pour éviter le re-render
 *  à chaque frappe sur les gros snapshots Discover (~1000 items). */
let _searchDebounce = null;
const wireSearch = () => {
  const input = document.querySelector("#tendances-search");
  const clear = document.querySelector("#tendances-search-clear");
  if (!input) return;

  const apply = () => {
    state.query = normalize(input.value.trim());
    clear.hidden = !input.value;
    recomputeCounts();
    // Re-render le panel actif avec le nouveau filtre
    showSource(state.active);
  };

  input.addEventListener("input", () => {
    clearTimeout(_searchDebounce);
    _searchDebounce = setTimeout(apply, 200);
  });

  // Esc = effacer
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
  // Wire les onglets
  document.querySelectorAll(".source-tab").forEach((tab) => {
    tab.addEventListener("click", () => showSource(tab.dataset.source));
  });

  // Câblage de la barre de recherche
  wireSearch();

  // Affiche par défaut Discover (le plus pertinent côté produit)
  await showSource("discover");

  // Récupère les compteurs en arrière-plan (tous les onglets en parallèle)
  updateCounts();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
