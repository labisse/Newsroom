/* ===================================================================
   Rendu des clusters éditoriaux (catégories + clusters d'entités +
   entités résiduelles).

   Tous les éléments sont CLIQUABLES via data attributes :
     - data-filter-kind  : "category" | "entity" | "entity-cluster"
     - data-filter-value : la clé (ex. path Discover, nom d'entité)
     - data-filter-extra : pour les clusters, les membres séparés par |

   briefing.js attache les click handlers (cf attachClusterFilters).
   =================================================================== */

import { h } from "./utils.js?v=tbr5";

/* ----- Catégories ----- */

export const renderCategories = (categories) => {
  if (!Array.isArray(categories) || categories.length === 0) return null;
  const maxScore = Math.max(...categories.map((c) => c.total_score || 0));

  return h(
    "section",
    { class: "clusters-section" },
    h(
      "div",
      { class: "clusters-section__head" },
      h("h2", { class: "clusters-section__title" }, "Catégories qui performent"),
      h(
        "span",
        { class: "clusters-section__hint" },
        "Clique pour filtrer les sujets",
      ),
    ),
    h(
      "ul",
      { class: "categories-grid" },
      ...categories.map((cat) => renderCategoryCard(cat, maxScore)),
    ),
  );
};

const renderCategoryCard = (cat, maxScore) => {
  const fill = maxScore > 0 ? Math.round((cat.total_score / maxScore) * 100) : 0;
  const tier =
    cat.avg_score >= 8 ? "high" : cat.avg_score >= 3 ? "medium" : "low";

  return h(
    "li",
    {
      class: "category-card",
      "data-tier": tier,
      "data-filter-kind": "category",
      "data-filter-value": cat.key,
      "data-filter-label": cat.label,
      role: "button",
      tabindex: "0",
    },
    h(
      "div",
      { class: "category-card__head" },
      h("h3", { class: "category-card__label" }, cat.label),
      h(
        "span",
        { class: "category-card__avg" },
        `avg ${cat.avg_score.toFixed(1)}`,
      ),
    ),
    h(
      "div",
      { class: "category-card__stats" },
      h(
        "div",
        { class: "category-card__stat" },
        h("span", { class: "category-card__stat-label" }, "Articles"),
        h(
          "span",
          { class: "category-card__stat-value" },
          String(cat.articles_count),
        ),
      ),
      h(
        "div",
        { class: "category-card__stat" },
        h("span", { class: "category-card__stat-label" }, "Score total"),
        h(
          "span",
          { class: "category-card__stat-value" },
          cat.total_score.toFixed(0),
        ),
      ),
    ),
    h(
      "div",
      { class: "category-card__bar" },
      h("span", {
        class: "category-card__bar-fill",
        style: `width: ${fill}%`,
      }),
    ),
    cat.top_articles?.length
      ? h(
          "ul",
          { class: "category-card__top" },
          ...cat.top_articles.slice(0, 2).map((a) =>
            h(
              "li",
              { class: "category-card__top-item" },
              h(
                "span",
                { class: "category-card__top-pub" },
                a.publisher || "—",
              ),
              h("span", { class: "category-card__top-title" }, a.title || ""),
            ),
          ),
        )
      : null,
  );
};

/* ----- Clusters d'entités (co-occurrence) ----- */

export const renderEntityClusters = (clusters) => {
  if (!Array.isArray(clusters) || clusters.length === 0) return null;

  return h(
    "section",
    { class: "clusters-section" },
    h(
      "div",
      { class: "clusters-section__head" },
      h("h2", { class: "clusters-section__title" }, "Univers à creuser"),
      h(
        "span",
        { class: "clusters-section__hint" },
        "Entités liées · clique pour filtrer",
      ),
    ),
    h(
      "ul",
      { class: "entity-cluster-grid" },
      ...clusters.map((c) => renderEntityClusterCard(c)),
    ),
  );
};

const renderEntityClusterCard = (cluster) => {
  // Sum-of-scores rescale x100/65 comme les scores individuels.
  const tier =
    cluster.total_score >= 46
      ? "high"
      : cluster.total_score >= 15
        ? "medium"
        : "low";
  const members = cluster.members || [];

  return h(
    "li",
    {
      class: "entity-cluster-card",
      "data-tier": tier,
      "data-filter-kind": "entity-cluster",
      "data-filter-value": cluster.label,
      "data-filter-label": cluster.label,
      "data-filter-extra": members.join("|"),
      role: "button",
      tabindex: "0",
    },
    h(
      "div",
      { class: "entity-cluster-card__head" },
      h("h3", { class: "entity-cluster-card__label" }, cluster.label),
      h(
        "span",
        { class: "entity-cluster-card__score" },
        cluster.total_score.toFixed(0),
      ),
    ),
    h(
      "div",
      { class: "entity-cluster-card__members" },
      ...members.map((m) =>
        h("span", { class: "entity-cluster-card__member" }, m),
      ),
    ),
    h(
      "div",
      { class: "entity-cluster-card__meta" },
      h(
        "span",
        {},
        `${cluster.articles_count} article${cluster.articles_count > 1 ? "s" : ""}`,
      ),
      h("span", {}, `${members.length} entité${members.length > 1 ? "s" : ""}`),
    ),
  );
};

/* ----- Entités résiduelles (hors clusters) ----- */

export const renderEntities = (entities) => {
  if (!Array.isArray(entities) || entities.length === 0) return null;

  return h(
    "section",
    { class: "clusters-section" },
    h(
      "div",
      { class: "clusters-section__head" },
      h("h2", { class: "clusters-section__title" }, "Topics individuels"),
      h(
        "span",
        { class: "clusters-section__hint" },
        "Entités isolées · clique pour filtrer",
      ),
    ),
    h(
      "ul",
      { class: "entities-cloud" },
      ...entities.map((ent) => renderEntityPill(ent)),
    ),
  );
};

const renderEntityPill = (ent) => {
  const tier =
    ent.total_score >= 40 ? "high" : ent.total_score >= 15 ? "medium" : "low";

  return h(
    "li",
    {
      class: "entity-pill",
      "data-tier": tier,
      "data-filter-kind": "entity",
      "data-filter-value": ent.name,
      "data-filter-label": ent.name,
      role: "button",
      tabindex: "0",
      title: ent.top_articles?.[0]?.title || ent.name,
    },
    h("span", { class: "entity-pill__name" }, ent.name),
    h(
      "span",
      { class: "entity-pill__meta" },
      h(
        "span",
        { class: "entity-pill__count" },
        `${ent.articles_count} art.`,
      ),
      h(
        "span",
        { class: "entity-pill__score" },
        ent.total_score.toFixed(0),
      ),
    ),
  );
};
