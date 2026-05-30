/* ===================================================================
   Daily Briefing — flux Discover global + filtrage par cat/entité/cluster.

   Sujets viennent du backend (data/sujets/latest.json).
   Pas de rédacteur attaché (HP neutre, projets par site séparés).
*/

import { tierFromScore, tierLabel } from "./data.js?v=tbr5";
import { loadSujets, formatFreshness, formatLongDate } from "./api.js?v=tbr5";
import {
  h,
  renderScore,
  renderSignal,
  renderTierDivider,
  chevronSvg,
} from "./utils.js?v=tbr5";
import {
  renderCategories,
  renderEntityClusters,
  renderEntities,
} from "./clusters.js?v=tbr5";

/* ===================================================================
   State global pour le filtrage par clic
   =================================================================== */

const state = {
  allSujets: [],
  // Buckets clusters bruts (catégories, clusters d'entités, entités plates)
  // → utilisés pour piocher les top_articles Discover quand un filtre actif
  //   ne ramène aucun sujet MSN (cf bug "5 ART → 0 SUJET").
  categoriesTrending: [],
  entityClusters: [],
  entitiesTrending: [],
  filter: null, // { kind: "category" | "entity" | "entity-cluster", value: string, label: string, members?: string[] }
};

/* ===================================================================
   Sujet row + détail
   =================================================================== */

const renderSujet = (sujet) => {
  const row = h(
    "li",
    { class: "sujet", "data-id": sujet.id },
    h("span", { class: "sujet__rank" }, String(sujet.rank).padStart(2, "0")),
    renderScore(sujet.score),
    h(
      "div",
      { class: "sujet__head" },
      h("h3", { class: "sujet__title" }, sujet.title),
      h(
        "div",
        { class: "sujet__meta" },
        h("span", { class: "sujet__theme" }, sujet.theme),
        h(
          "div",
          { class: "sujet__signals" },
          ...sujet.signals.slice(0, 4).map((s) => renderSignal(s)),
        ),
      ),
    ),
    h("button", { class: "sujet__chevron", "aria-label": "Voir détail" }, chevronSvg()),
    renderDetail(sujet),
  );

  row.addEventListener("click", (e) => {
    if (e.target.closest("button")?.classList.contains("btn")) return;
    row.classList.toggle("is-expanded");
  });

  return row;
};

const renderDetail = (sujet) => {
  const sourceRows = sujet.sources.map((src) =>
    h(
      "div",
      { class: "detail-source-row" },
      h("span", { class: "detail-source-row__name" }, src.name),
      h("span", {
        class: "detail-source-row__bar",
        style: `--bar-empty: ${100 - src.fill}%`,
      }),
      h("span", { class: "detail-source-row__value" }, src.value),
    ),
  );

  // Chaque ref peut être :
  //   - string (ancien format) → on tombe en fallback sur msn_url
  //   - { label, url }          → chaque ref a son propre lien
  const refs = sujet.refs?.length
    ? h(
        "div",
        { class: "detail-sources", style: "margin-top: 24px" },
        h("span", { class: "detail-col__label" }, "Articles de référence"),
        ...sujet.refs.map((r) => {
          const isObj = r && typeof r === "object";
          const label = isObj ? r.label : r;
          const url = isObj ? r.url : sujet.msn_url;
          return h(
            "div",
            { class: "detail-source-row", style: "grid-template-columns: 1fr" },
            url
              ? h(
                  "a",
                  {
                    class: "detail-source-row__name",
                    href: url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                  },
                  label,
                )
              : h("span", { class: "detail-source-row__name" }, label),
          );
        }),
      )
    : null;

  return h(
    "div",
    { class: "sujet__detail" },
    h(
      "div",
      { class: "detail-col" },
      h("p", { class: "detail-rationale" }, sujet.rationale),
      h(
        "div",
        { class: "detail-sources" },
        h("span", { class: "detail-col__label" }, "Signaux détaillés"),
        ...sourceRows,
      ),
      refs,
    ),
    h(
      "div",
      { class: "detail-actions" },
      h(
        "button",
        {
          class: "btn btn--ghost btn--sm",
          onClick: (e) => {
            e.stopPropagation();
            action("reject", sujet);
          },
        },
        "Rejeter",
      ),
      h(
        "button",
        {
          class: "btn btn--ghost btn--sm",
          onClick: (e) => {
            e.stopPropagation();
            action("save", sujet);
          },
        },
        "Sauvegarder",
      ),
      h(
        "button",
        {
          class: "btn btn--primary btn--sm",
          onClick: (e) => {
            e.stopPropagation();
            action("validate", sujet);
          },
        },
        "Valider",
      ),
    ),
  );
};

const action = (kind, sujet) => {
  const labels = {
    validate: "Validé",
    save: "Sauvegardé pour projet",
    reject: "Rejeté",
  };
  toast(`${labels[kind]} · ${sujet.title.slice(0, 60)}${sujet.title.length > 60 ? "…" : ""}`);
};

/* ===================================================================
   Toast
   =================================================================== */

const toast = (message) => {
  let host = document.querySelector(".toast-host");
  if (!host) {
    host = h("div", { class: "toast-host" });
    document.body.appendChild(host);
  }
  const item = h("div", { class: "toast" }, message);
  host.appendChild(item);
  requestAnimationFrame(() => item.classList.add("is-visible"));
  setTimeout(() => {
    item.classList.remove("is-visible");
    setTimeout(() => item.remove(), 240);
  }, 2400);
};

/* ===================================================================
   States loading / error
   =================================================================== */

const renderLoading = () =>
  h(
    "li",
    { class: "briefing-state" },
    h("span", { class: "briefing-state__spinner" }),
    "Chargement des signaux…",
  );

const renderError = (message) =>
  h(
    "li",
    { class: "briefing-state briefing-state--error" },
    h("strong", {}, "Données indisponibles."),
    h("span", {}, message),
  );

const renderEmptyFilter = () =>
  h(
    "li",
    { class: "briefing-state" },
    h("strong", {}, "Aucun sujet ne correspond au filtre."),
    h(
      "span",
      {},
      "Essaie une autre catégorie / topic, ou efface le filtre actif.",
    ),
  );

/* ===================================================================
   Filtrage
   =================================================================== */

const matchesFilter = (sujet, filter) => {
  if (!filter) return true;
  const cat = sujet.discover_category || "";
  const ents = sujet.discover_entities || [];

  if (filter.kind === "category") {
    return cat === filter.value;
  }
  if (filter.kind === "entity") {
    return ents.includes(filter.value);
  }
  if (filter.kind === "entity-cluster") {
    // L'un des membres du cluster doit matcher au moins une des entités du sujet
    const members = filter.members || [filter.value];
    return ents.some((e) => members.includes(e));
  }
  return true;
};

/**
 * Récupère les top_articles Discover du bucket qui correspond au filtre actif.
 * Les sujets MSN (top 30) ne couvrent qu'une fraction des entités/catégories
 * vues en Discover (1200+ articles) — quand aucun sujet MSN ne matche, on
 * affiche directement les articles Discover qui ont fait grimper le compteur
 * (cf bug "5 ART → 0 SUJET").
 *
 * Dédup contre les sujets MSN déjà affichés (par URL ou titre normalisé).
 */
const discoverArticlesForFilter = (filter, msnUrls) => {
  if (!filter) return [];
  let bucket = null;
  if (filter.kind === "category") {
    bucket = state.categoriesTrending.find((c) => c.key === filter.value);
  } else if (filter.kind === "entity") {
    bucket = state.entitiesTrending.find((e) => e.name === filter.value);
  } else if (filter.kind === "entity-cluster") {
    bucket = state.entityClusters.find((c) => c.label === filter.value);
  }
  if (!bucket) return [];
  const articles = bucket.top_articles || [];
  return articles.filter((a) => {
    const url = a.url || "";
    return url && !msnUrls.has(url);
  });
};

const renderDiscoverArticle = (article) => {
  // Carte minimaliste : un article Discover repéré dans le flux mais
  // pas encore promu en sujet global. Visuellement distinct du sujet MSN
  // pour ne pas tromper le rédac chef sur le statut éditorial.
  const score = Number(article.score || 0);
  const scoreDisplay =
    score >= 10 ? score.toFixed(0) : score >= 1 ? score.toFixed(1) : "présent";
  return h(
    "li",
    { class: "sujet sujet--discover-only" },
    h(
      "span",
      { class: "sujet__rank sujet__rank--discover" },
      "DIS",
    ),
    h(
      "div",
      { class: "sujet__discover-score", title: "Score Discoversnoop" },
      h("span", { class: "sujet__discover-score-value" }, String(scoreDisplay)),
      h("span", { class: "sujet__discover-score-label" }, "/65"),
    ),
    h(
      "div",
      { class: "sujet__head" },
      article.url
        ? h(
            "a",
            {
              class: "sujet__title sujet__title--link",
              href: article.url,
              target: "_blank",
              rel: "noopener noreferrer",
            },
            article.title || "(sans titre)",
          )
        : h("h3", { class: "sujet__title" }, article.title || "(sans titre)"),
      h(
        "div",
        { class: "sujet__meta" },
        h(
          "span",
          { class: "sujet__theme" },
          article.publisher || "Discover",
        ),
        h(
          "span",
          { class: "signal-pill", "data-source": "gsc" },
          "discover · non promu MSN",
        ),
      ),
    ),
  );
};

const setFilter = (filter) => {
  state.filter = filter;
  refreshList();
  updateFilterBanner();
  updateFilterHighlight();
};

const clearFilter = () => setFilter(null);

const updateFilterBanner = () => {
  const banner = document.querySelector("#filter-banner");
  if (!banner) return;

  if (!state.filter) {
    banner.classList.remove("is-active");
    banner.innerHTML = "";
    return;
  }

  const visible = state.allSujets.filter((s) => matchesFilter(s, state.filter));
  const msnUrls = new Set(visible.map((s) => s.msn_url || "").filter(Boolean));
  const discoverExtras = discoverArticlesForFilter(state.filter, msnUrls);
  const kindLabel = {
    category: "Catégorie",
    entity: "Topic",
    "entity-cluster": "Univers",
  }[state.filter.kind];

  // Compteur unifié : sujets MSN scorés + articles Discover non promus
  const countParts = [];
  if (visible.length > 0) {
    countParts.push(`${visible.length} sujet${visible.length > 1 ? "s" : ""}`);
  }
  if (discoverExtras.length > 0) {
    countParts.push(
      `${discoverExtras.length} article${discoverExtras.length > 1 ? "s" : ""} Discover`,
    );
  }
  const countText = countParts.length ? countParts.join(" · ") : "0 sujet";

  banner.classList.add("is-active");
  banner.innerHTML = "";
  banner.appendChild(
    h(
      "div",
      { class: "filter-banner__inner" },
      h("span", { class: "filter-banner__kind" }, kindLabel),
      h("span", { class: "filter-banner__value" }, state.filter.label),
      h("span", { class: "filter-banner__count" }, countText),
      h(
        "button",
        {
          class: "filter-banner__clear",
          type: "button",
          onClick: clearFilter,
        },
        "Effacer ✕",
      ),
    ),
  );
};

const updateFilterHighlight = () => {
  document.querySelectorAll("[data-filter-kind]").forEach((el) => {
    el.classList.remove("is-active");
  });
  if (!state.filter) return;
  const selector = `[data-filter-kind="${state.filter.kind}"][data-filter-value="${cssEscape(
    state.filter.value,
  )}"]`;
  document.querySelectorAll(selector).forEach((el) => {
    el.classList.add("is-active");
  });
};

// Échappe une valeur pour usage dans un attribute selector CSS
const cssEscape = (value) =>
  String(value).replace(/(["\\])/g, "\\$1");

const attachClusterFilters = () => {
  const handler = (event) => {
    const target = event.target.closest("[data-filter-kind]");
    if (!target) return;
    if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();

    const kind = target.dataset.filterKind;
    const value = target.dataset.filterValue;
    const label = target.dataset.filterLabel || value;
    const extra = target.dataset.filterExtra;
    const members = extra ? extra.split("|").filter(Boolean) : undefined;

    // Toggle : re-clic sur le même filtre = clear
    if (
      state.filter &&
      state.filter.kind === kind &&
      state.filter.value === value
    ) {
      clearFilter();
      return;
    }

    setFilter({ kind, value, label, members });
    // Scroller la liste des sujets pour voir le résultat
    document
      .querySelector(".sujet-list")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const mount = document.querySelector("#clusters-mount");
  if (!mount) return;
  mount.addEventListener("click", handler);
  mount.addEventListener("keydown", handler);
};

/* ===================================================================
   Render de la liste des sujets (avec ou sans filtre)
   =================================================================== */

const refreshList = () => {
  const list = document.querySelector("#sujet-list");
  list.innerHTML = "";

  const filtered = state.allSujets.filter((s) => matchesFilter(s, state.filter));

  // Sujets MSN matchés, regroupés par tier
  const sorted = [...filtered].sort((a, b) => b.score - a.score);
  const buckets = { high: [], medium: [], low: [] };
  for (const s of sorted) buckets[tierFromScore(s.score)].push(s);
  for (const tier of ["high", "medium", "low"]) {
    if (buckets[tier].length === 0) continue;
    list.appendChild(renderTierDivider(tierLabel[tier], buckets[tier].length));
    for (const s of buckets[tier]) list.appendChild(renderSujet(s));
  }

  // Articles Discover du bucket filtré qui ne sont PAS déjà couverts par
  // un sujet MSN (cf bug "5 ART → 0 SUJET"). On dédup par URL pour ne
  // pas afficher deux fois un article qui aurait été matché en MSN.
  if (state.filter) {
    const msnUrls = new Set(
      filtered.map((s) => s.msn_url || "").filter(Boolean),
    );
    const discoverArticles = discoverArticlesForFilter(state.filter, msnUrls);
    if (discoverArticles.length > 0) {
      list.appendChild(
        renderTierDivider(
          `Articles Discover · non promus en sujet MSN`,
          discoverArticles.length,
        ),
      );
      for (const a of discoverArticles) {
        list.appendChild(renderDiscoverArticle(a));
      }
    } else if (filtered.length === 0) {
      // Vraie absence de signal (rare) : pas de sujet MSN, pas d'article
      // Discover dans le bucket → message d'orientation.
      list.appendChild(renderEmptyFilter());
    }
  }
};

const setCounts = (sujets, sourcesUsed) => {
  const counts = sujets.reduce(
    (acc, s) => {
      acc[tierFromScore(s.score)] += 1;
      return acc;
    },
    { high: 0, medium: 0, low: 0 },
  );
  // Anciennes pills (compatibilité si présentes ailleurs)
  document.querySelector("#count-total")?.textContent &&
    (document.querySelector("#count-total").textContent = String(sujets.length));
  document.querySelector("#count-high") &&
    (document.querySelector("#count-high").textContent = String(counts.high));
  document.querySelector("#count-medium") &&
    (document.querySelector("#count-medium").textContent = String(counts.medium));
  document.querySelector("#count-low") &&
    (document.querySelector("#count-low").textContent = String(counts.low));

  // KPI tiles cockpit
  const $hot = document.querySelector("#kpi-hot");
  const $total = document.querySelector("#kpi-total");
  const $sources = document.querySelector("#kpi-sources");
  if ($hot) $hot.textContent = String(counts.high);
  if ($total) $total.textContent = String(sujets.length);
  if ($sources && sourcesUsed) {
    // Une source = "active" si count > 0 dans ce snapshot
    const active = Object.values(sourcesUsed).filter(
      (s) => (s?.count ?? 0) > 0,
    ).length;
    const total = Object.keys(sourcesUsed).length;
    $sources.textContent = `${active}/${total}`;
  }
};

/* Topics qui montent — depuis data/analytics/evolution.json (peuplé par
   le pipeline CI toutes les 6h après db-export). */
const loadEvolution = async () => {
  try {
    const r = await fetch("data/analytics/evolution.json", { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
};

const setRisingTopics = (evolution) => {
  const container = document.querySelector("#rising-topics");
  if (!container) return;
  container.innerHTML = "";

  if (!evolution?.available) {
    container.innerHTML = `<div class="rising-topics__empty">Pas encore d'historique (1er snapshot DB en attente).</div>`;
    return;
  }
  const topics = (evolution.topics_24h || [])
    .filter((t) => t.delta > 0 || t.prev_count === 0)
    .slice(0, 8);

  const $kpiRising = document.querySelector("#kpi-rising");
  if ($kpiRising) $kpiRising.textContent = String(topics.length);

  if (topics.length === 0) {
    container.innerHTML = `<div class="rising-topics__empty">Rien ne monte significativement sur les dernières 24h.</div>`;
    return;
  }

  const ul = document.createElement("ul");
  ul.className = "rising-topics__list";
  for (const t of topics) {
    const isNew = t.prev_count === 0;
    const li = document.createElement("li");
    li.className = "rising-topic" + (isNew ? " rising-topic--new" : "");
    li.innerHTML = `
      <span class="rising-topic__kind" data-kind="${t.topic_kind}">${t.topic_kind === "entity" ? "ENT" : t.topic_kind === "cluster" ? "CLU" : "CAT"}</span>
      <span class="rising-topic__name">${escapeHtml(t.topic_label || t.topic_name)}</span>
      <span class="rising-topic__delta">${isNew ? "NEW" : "+" + t.delta}</span>
    `;
    ul.appendChild(li);
  }
  container.appendChild(ul);
};

const setSourcePulse = (evolution) => {
  const container = document.querySelector("#source-pulse");
  if (!container) return;
  container.innerHTML = "";

  const timeline = evolution?.source_timeline_7d;
  if (!timeline || Object.keys(timeline).length === 0) {
    container.innerHTML = `<div class="rising-topics__empty">Sparklines en attente (besoin de 2+ snapshots).</div>`;
    return;
  }

  const SOURCE_COLORS = {
    discover: "#00FF00",
    discoversnoop: "#00FF00",
    gnews: "#4285F4",
    google_news: "#4285F4",
    reddit: "#FF4500",
    youtube: "#FF0033",
    youtube_trending: "#FF0033",
    trends: "#FBBC04",
    google_trends: "#FBBC04",
    wikimedia: "#FFFFFF",
    x_trends: "#00FFFF",
    msn: "#00A4EF",
  };
  const SOURCE_LABELS = {
    discoversnoop: "Discover",
    google_news: "GNews",
    youtube_trending: "YouTube",
    google_trends: "Trends",
    wikimedia: "Wiki",
    x_trends: "X",
    msn: "MSN",
    reddit: "Reddit",
  };

  for (const src of Object.keys(timeline).sort()) {
    const points = timeline[src];
    if (points.length < 1) continue;
    const latest = points[points.length - 1]?.count ?? 0;
    const color = SOURCE_COLORS[src] || "#FFF";
    const label = SOURCE_LABELS[src] || src;

    // Sparkline SVG
    const w = 70, ht = 20;
    let line = "";
    if (points.length >= 2) {
      const max = Math.max(1, ...points.map((p) => p.count));
      const min = Math.min(...points.map((p) => p.count));
      const range = Math.max(1, max - min);
      const step = w / (points.length - 1);
      line = points
        .map((p, i) => {
          const x = i * step;
          const y = ht - ((p.count - min) / range) * (ht - 2) - 1;
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
    }

    const row = document.createElement("div");
    row.className = "pulse-row";
    row.innerHTML = `
      <span class="pulse-row__name" style="color:${color}">${label}</span>
      <svg class="pulse-row__spark" viewBox="0 0 ${w} ${ht}" preserveAspectRatio="none">
        ${line ? `<polyline points="${line}" fill="none" stroke="${color}" stroke-width="1.2"/>` : ""}
      </svg>
      <span class="pulse-row__count">${latest}</span>
    `;
    container.appendChild(row);
  }
};

const escapeHtml = (s) =>
  String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const setFreshness = (generatedAt) => {
  const el = document.querySelector("#briefing-freshness");
  if (el && generatedAt) {
    el.textContent = `Pipeline actif · ${formatFreshness(generatedAt)}`;
  }
  const dateEl = document.querySelector("#briefing-date");
  if (dateEl && generatedAt) {
    const long = formatLongDate(generatedAt);
    dateEl.textContent = long ? long.charAt(0).toUpperCase() + long.slice(1) : "";
  }
};

/* ===================================================================
   Mount
   =================================================================== */

const mount = async () => {
  const list = document.querySelector("#sujet-list");
  list.innerHTML = "";
  list.appendChild(renderLoading());

  let data;
  try {
    data = await loadSujets();
  } catch (err) {
    list.innerHTML = "";
    list.appendChild(renderError(err.message || "Erreur inconnue."));
    return;
  }

  const {
    sujets,
    generatedAt,
    sources,
    categoriesTrending,
    entityClusters,
    entitiesTrending,
  } = data;

  state.allSujets = sujets;
  state.categoriesTrending = categoriesTrending || [];
  state.entityClusters = entityClusters || [];
  state.entitiesTrending = entitiesTrending || [];

  // Sections clusters : Catégories + Clusters d'entités + Entités résiduelles
  const clustersMount = document.querySelector("#clusters-mount");
  if (clustersMount) {
    clustersMount.innerHTML = "";
    const catsNode = renderCategories(categoriesTrending);
    if (catsNode) clustersMount.appendChild(catsNode);
    const clustersNode = renderEntityClusters(entityClusters);
    if (clustersNode) clustersMount.appendChild(clustersNode);
    const entsNode = renderEntities(entitiesTrending);
    if (entsNode) clustersMount.appendChild(entsNode);
  }

  attachClusterFilters();
  refreshList();
  setCounts(sujets, sources);
  setFreshness(generatedAt);

  // Cockpit : sidebar live depuis analytics (en parallèle, non bloquant)
  loadEvolution().then((evo) => {
    setRisingTopics(evo);
    setSourcePulse(evo);
  });

  document.querySelector("#export-btn")?.addEventListener("click", () => {
    toast("Briefing exporté (PDF + lien partage)");
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
