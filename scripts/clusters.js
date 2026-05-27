/* ===================================================================
   Rendu des clusters éditoriaux (catégories + entités).

   Sources : payload.categories_trending + payload.entities_trending
   (produits par server/scoring/clusters.py, exposés via api.js).

   Objectif UX : montrer au rédac chef les **univers** qui performent,
   pas seulement les sujets individuels. Un rédacteur peut être driver
   sur une catégorie ou une entité sans qu'un sujet spécifique sorte.
   =================================================================== */

import { h } from "./utils.js?v=tbr4";

/* ----- Catégories (cards "stat-card-like") ----- */

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
        "Lignes éditoriales tendance",
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
  // Hauteur de barre relative au max
  const fill = maxScore > 0 ? Math.round((cat.total_score / maxScore) * 100) : 0;
  const tier =
    cat.avg_score >= 8
      ? "high"
      : cat.avg_score >= 3
        ? "medium"
        : "low";

  return h(
    "li",
    { class: "category-card", "data-tier": tier },
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

/* ----- Entités (pills/tags) ----- */

export const renderEntities = (entities) => {
  if (!Array.isArray(entities) || entities.length === 0) return null;

  return h(
    "section",
    { class: "clusters-section" },
    h(
      "div",
      { class: "clusters-section__head" },
      h(
        "h2",
        { class: "clusters-section__title" },
        "Topics tendances",
      ),
      h(
        "span",
        { class: "clusters-section__hint" },
        "Entités à creuser",
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
