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

  const refs = sujet.refs?.length
    ? h(
        "div",
        { class: "detail-sources", style: "margin-top: 24px" },
        h("span", { class: "detail-col__label" }, "Articles de référence"),
        ...sujet.refs.map((r) =>
          h(
            "div",
            { class: "detail-source-row", style: "grid-template-columns: 1fr" },
            sujet.msn_url
              ? h(
                  "a",
                  {
                    class: "detail-source-row__name",
                    href: sujet.msn_url,
                    target: "_blank",
                    rel: "noopener noreferrer",
                  },
                  r,
                )
              : h("span", { class: "detail-source-row__name" }, r),
          ),
        ),
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
  const kindLabel = {
    category: "Catégorie",
    entity: "Topic",
    "entity-cluster": "Univers",
  }[state.filter.kind];

  banner.classList.add("is-active");
  banner.innerHTML = "";
  banner.appendChild(
    h(
      "div",
      { class: "filter-banner__inner" },
      h("span", { class: "filter-banner__kind" }, kindLabel),
      h("span", { class: "filter-banner__value" }, state.filter.label),
      h(
        "span",
        { class: "filter-banner__count" },
        `${visible.length} sujet${visible.length > 1 ? "s" : ""}`,
      ),
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

  if (filtered.length === 0) {
    list.appendChild(renderEmptyFilter());
    return;
  }

  const sorted = [...filtered].sort((a, b) => b.score - a.score);
  const buckets = { high: [], medium: [], low: [] };
  for (const s of sorted) buckets[tierFromScore(s.score)].push(s);

  for (const tier of ["high", "medium", "low"]) {
    if (buckets[tier].length === 0) continue;
    list.appendChild(renderTierDivider(tierLabel[tier], buckets[tier].length));
    for (const s of buckets[tier]) list.appendChild(renderSujet(s));
  }
};

const setCounts = (sujets) => {
  const counts = sujets.reduce(
    (acc, s) => {
      acc[tierFromScore(s.score)] += 1;
      return acc;
    },
    { high: 0, medium: 0, low: 0 },
  );
  document.querySelector("#count-total").textContent = String(sujets.length);
  document.querySelector("#count-high").textContent = String(counts.high);
  document.querySelector("#count-medium").textContent = String(counts.medium);
  document.querySelector("#count-low").textContent = String(counts.low);
};

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
    categoriesTrending,
    entityClusters,
    entitiesTrending,
  } = data;

  state.allSujets = sujets;

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
  setCounts(sujets);
  setFreshness(generatedAt);

  document.querySelector("#export-btn")?.addEventListener("click", () => {
    toast("Briefing exporté (PDF + lien partage)");
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
