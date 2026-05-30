/* ===================================================================
   Page projet individuel — lit ?slug=, affiche les infos + insights GSC.

   Comportement :
     1. Charge data/projects/index.json pour les méta du projet
     2. Tente de charger data/projects/{slug}/insights.json
        - Si OK → affiche stats + top URLs + insights RAG croisés
        - Si 404 → affiche le placeholder "GSC en attente"
   =================================================================== */

import { h } from "./utils.js?v=tbr7";

const PROJECTS_URL = "/data/projects/index.json";
const insightsUrl = (slug) => `/data/projects/${slug}/insights.json`;

/* ----- Helpers ----- */

const setText = (selector, value) => {
  const el = document.querySelector(selector);
  if (el) el.textContent = value;
};

const formatNumber = (n) => {
  if (n == null) return "—";
  return Number(n).toLocaleString("fr-FR").replace(/ /g, " ");
};

const formatPercent = (n) => {
  if (n == null) return "—";
  return `${(n * 100).toFixed(1)}%`;
};

const truncate = (s, n) =>
  s && s.length > n ? s.slice(0, n - 1) + "…" : s || "";

const showError = (message) => {
  const main = document.querySelector("#project-main");
  const errorBox = document.querySelector("#project-error");
  if (!main || !errorBox) return;
  main.querySelectorAll("section").forEach((el) => (el.style.display = "none"));
  document.querySelector("#project-insights").style.display = "none";
  errorBox.style.display = "block";
  errorBox.innerHTML = "";
  errorBox.appendChild(
    h(
      "div",
      { class: "project-empty project-empty--error" },
      h("strong", {}, "Projet introuvable."),
      h("p", {}, message),
      h(
        "p",
        { style: "margin-top: 16px" },
        h(
          "a",
          { href: "projects.html", class: "btn btn--ghost btn--sm" },
          "← Retour aux projets",
        ),
      ),
    ),
  );
};

const renderThemes = (themes) => {
  const container = document.querySelector("#project-themes");
  if (!container || !Array.isArray(themes)) return;
  container.innerHTML = "";
  for (const theme of themes) {
    container.appendChild(
      h("span", { class: "project-card__theme" }, theme),
    );
  }
};

/* ----- Rendu insights ----- */

const renderStats = (stats, generatedAt) => {
  const container = document.querySelector("#project-stats");
  if (!container) return;
  container.innerHTML = "";

  const cards = [
    {
      value: formatNumber(stats.total_urls),
      label: "URLs Discover · 12 mois",
    },
    {
      value: formatNumber(stats.total_clicks),
      label: "Clicks Discover cumulés",
      accent: true,
    },
    {
      value: formatNumber(stats.with_title),
      sub: `/ ${formatNumber(stats.total_urls)}`,
      label: "Titres scrapés",
    },
    {
      value: generatedAt ? formatRelative(generatedAt) : "—",
      label: "Insights générés",
    },
  ];

  for (const c of cards) {
    container.appendChild(
      h(
        "div",
        { class: "project-stat-card" + (c.accent ? " is-accent" : "") },
        h(
          "div",
          { class: "project-stat-card__value" },
          c.value,
          c.sub ? h("span", { class: "project-stat-card__sub" }, " " + c.sub) : null,
        ),
        h("div", { class: "project-stat-card__label" }, c.label),
      ),
    );
  }
};

const formatRelative = (iso) => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const diffMin = Math.round((Date.now() - date.getTime()) / 60_000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  if (diffMin < 60 * 24) return `il y a ${Math.round(diffMin / 60)} h`;
  return `il y a ${Math.round(diffMin / (60 * 24))} j`;
};

const renderTopUrls = (topUrls) => {
  const list = document.querySelector("#project-top-list");
  const meta = document.querySelector("#project-top-meta");
  if (!list) return;
  list.innerHTML = "";
  if (meta) meta.textContent = `${topUrls.length} URLs · triées par clicks`;

  topUrls.forEach((item, idx) => {
    list.appendChild(
      h(
        "li",
        { class: "project-top-item" },
        h(
          "span",
          { class: "project-top-item__rank" },
          String(idx + 1).padStart(2, "0"),
        ),
        h(
          "span",
          { class: "project-top-item__clicks" },
          formatNumber(item.clicks),
        ),
        h(
          "a",
          {
            class: "project-top-item__title",
            href: item.url,
            target: "_blank",
            rel: "noopener noreferrer",
            title: item.url,
          },
          item.title || urlToReadable(item.url),
        ),
      ),
    );
  });
};

const urlToReadable = (url) => {
  try {
    const parsed = new URL(url);
    const slug = parsed.pathname.split("/").filter(Boolean).pop() || parsed.pathname;
    return slug.replace(/[-_]+/g, " ").replace(/\b\d{4,}$/, "").trim() || url;
  } catch {
    return url;
  }
};

const renderRagGroups = (insights) => {
  const container = document.querySelector("#project-rag-groups");
  if (!container) return;
  container.innerHTML = "";

  // Onglets : catégories / clusters / entités
  const tabs = [
    {
      key: "by_category",
      label: "Catégories",
      items: insights.by_category || [],
      labelKey: "label",
      metaKey: "global_articles_count",
      metaLabel: "articles tendance",
    },
    {
      key: "by_entity_cluster",
      label: "Univers",
      items: insights.by_entity_cluster || [],
      labelKey: "label",
      extraKey: "members",
      metaKey: "global_articles_count",
      metaLabel: "articles tendance",
    },
    {
      key: "by_entity",
      label: "Entités",
      items: insights.by_entity || [],
      labelKey: "name",
      metaKey: "global_articles_count",
      metaLabel: "articles tendance",
    },
  ];

  // Tabs UI
  const tabsBar = h("div", { class: "project-rag__tabs" });
  const contentArea = h("div", { class: "project-rag__content" });
  container.appendChild(tabsBar);
  container.appendChild(contentArea);

  const activate = (idx) => {
    [...tabsBar.children].forEach((el, i) =>
      el.classList.toggle("is-active", i === idx),
    );
    contentArea.innerHTML = "";
    contentArea.appendChild(renderGroupContent(tabs[idx]));
  };

  tabs.forEach((tab, idx) => {
    tabsBar.appendChild(
      h(
        "button",
        {
          class: "project-rag__tab" + (idx === 0 ? " is-active" : ""),
          type: "button",
          onClick: () => activate(idx),
        },
        `${tab.label} (${tab.items.length})`,
      ),
    );
  });

  activate(0);
};

const renderGroupContent = (tab) => {
  if (!tab.items.length) {
    return h(
      "div",
      { class: "project-rag__empty" },
      h("strong", {}, "Aucun élément."),
      h("p", {}, "Le flux du jour ne contient pas cette dimension."),
    );
  }

  const grid = h("div", { class: "project-rag__group-grid" });
  for (const item of tab.items) {
    grid.appendChild(renderGroupCard(item, tab));
  }
  return grid;
};

const renderGroupCard = (item, tab) => {
  const matches = item.matches || [];
  const label = item[tab.labelKey] || "—";
  const members = tab.extraKey ? item[tab.extraKey] || [] : [];

  return h(
    "div",
    { class: "project-rag__card" },
    h(
      "div",
      { class: "project-rag__card-head" },
      h("h3", { class: "project-rag__card-label" }, label),
      h(
        "span",
        { class: "project-rag__card-meta" },
        `${item[tab.metaKey] || 0} ${tab.metaLabel}`,
      ),
    ),
    members.length
      ? h(
          "div",
          { class: "project-rag__card-members" },
          ...members.map((m) =>
            h("span", { class: "project-rag__card-member" }, m),
          ),
        )
      : null,
    matches.length
      ? h(
          "ul",
          { class: "project-rag__matches" },
          ...matches.map((m) => renderMatch(m)),
        )
      : h(
          "div",
          { class: "project-rag__no-match" },
          "Aucun contenu historique pertinent trouvé.",
        ),
  );
};

const renderMatch = (m) => {
  const sim = (m.similarity * 100).toFixed(0);
  const title = m.title || urlToReadable(m.url);
  return h(
    "li",
    { class: "project-rag__match" },
    h("span", { class: "project-rag__match-sim" }, `${sim}%`),
    h(
      "div",
      { class: "project-rag__match-body" },
      h(
        "a",
        {
          class: "project-rag__match-title",
          href: m.url,
          target: "_blank",
          rel: "noopener noreferrer",
        },
        truncate(title, 110),
      ),
      h(
        "span",
        { class: "project-rag__match-clicks" },
        `${formatNumber(m.clicks)} clicks`,
      ),
    ),
  );
};

/* ----- Main ----- */

const mount = async () => {
  const params = new URLSearchParams(window.location.search);
  const slug = params.get("slug");

  if (!slug) {
    showError("Aucun slug fourni dans l'URL (project.html?slug=…).");
    return;
  }

  // 1. Charge la config projet
  let projectsPayload;
  try {
    const res = await fetch(PROJECTS_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    projectsPayload = await res.json();
  } catch {
    showError("Impossible de charger data/projects/index.json.");
    return;
  }

  const project = (projectsPayload.projects || []).find(
    (p) => p.slug === slug,
  );
  if (!project) {
    showError(`Aucun projet ne correspond au slug "${slug}".`);
    return;
  }

  document.title = `${project.name} · Editorial Signal · The Black Room`;
  setText("#project-name", project.name);
  setText("#project-domain", project.domain || "");
  setText("#project-tagline", project.tagline || "");
  renderThemes(project.themes);

  // 2. Tente de charger insights.json
  let insights = null;
  try {
    const res = await fetch(insightsUrl(slug), { cache: "no-store" });
    if (res.ok) insights = await res.json();
  } catch {
    /* ignore */
  }

  if (insights) {
    document.querySelector("#project-insights").style.display = "block";
    document.querySelector("#project-pending").style.display = "none";

    // ★ Section principale : briefing personnalisé du projet
    renderBriefing(
      insights.scored_sujets || [],
      insights.project_tier_counts || { high: 0, medium: 0, low: 0 },
      insights.sujets_source,
      project.name,
      insights.topical_filter || null,
    );

    // Sections secondaires (Univers tendance / Top historique /
    // Performance GSC) retirées du layout pour alléger la page. Les
    // renderers restent disponibles si on veut les réactiver plus tard.
  } else {
    document.querySelector("#project-insights").style.display = "none";
    document.querySelector("#project-pending").style.display = "block";
  }
};

/* ----- Briefing personnalisé : liste re-triée + affinity badge ----- */

const renderBriefing = (
  scoredSujets,
  tierCounts,
  sujetsSource,
  projectName,
  topicalFilter,
) => {
  // Meta header
  const meta = document.querySelector("#project-briefing-meta");
  if (meta) {
    const srcDate = sujetsSource?.generated_at
      ? formatRelative(sujetsSource.generated_at)
      : "n/a";
    const total = topicalFilter?.total_candidates ?? scoredSujets.length;
    const excluded = topicalFilter?.excluded_off_topic ?? 0;
    const strict = topicalFilter?.strict_topical === true;

    let html =
      `<strong>${scoredSujets.length} sujets</strong> du flux global ` +
      `re-scorés avec ton historique Discover. ` +
      `Tri par <strong>Score ${projectName}</strong> ` +
      `(combinaison signal global × affinité historique).`;

    if (strict && excluded > 0) {
      html +=
        ` <span class="briefing-filter-note">` +
        `<strong>${excluded}/${total}</strong> sujets globaux écartés ` +
        `(hors territoire éditorial : catégorie ou thèmes du projet non concernés)` +
        `.</span>`;
    }
    html += ` <em>Flux global : ${srcDate}</em>.`;
    meta.innerHTML = html;
  }

  // Counts
  const countsEl = document.querySelector("#project-briefing-counts");
  if (countsEl) {
    countsEl.innerHTML = "";
    const labels = [
      { value: tierCounts.high, label: "fort", cls: "is-success" },
      { value: tierCounts.medium, label: "moyen", cls: "is-warning" },
      { value: tierCounts.low, label: "faible", cls: "is-danger" },
    ];
    for (const c of labels) {
      countsEl.appendChild(
        h(
          "span",
          { class: `project-briefing__count ${c.cls}` },
          h("strong", {}, String(c.value)),
          ` ${c.label}`,
        ),
      );
    }
  }

  // Liste
  const list = document.querySelector("#project-briefing-list");
  if (!list) return;
  list.innerHTML = "";

  if (!scoredSujets.length) {
    const strict = topicalFilter?.strict_topical === true;
    const total = topicalFilter?.total_candidates ?? 0;
    if (strict && total > 0) {
      list.appendChild(
        h(
          "li",
          { class: "project-empty" },
          h(
            "strong",
            {},
            "Aucun sujet du flux global ne touche votre territoire éditorial aujourd'hui.",
          ),
          h(
            "p",
            {},
            `${total} sujets analysés, tous écartés (catégories Discover et thèmes du projet non concernés). ` +
              "C'est un signal honnête : pas d'angle évident à creuser dans l'actu chaude.",
          ),
        ),
      );
    } else {
      list.appendChild(
        h(
          "li",
          { class: "project-empty" },
          h("strong", {}, "Aucun sujet à scorer."),
          h(
            "p",
            {},
            "Lance `python -m server.cli score` pour générer le flux global, puis re-génère les insights.",
          ),
        ),
      );
    }
    return;
  }

  for (const sujet of scoredSujets) {
    list.appendChild(renderBriefingSujet(sujet));
  }
};

const briefingTier = (score) =>
  score >= 50 ? "high" : score >= 30 ? "medium" : "low";

const renderBriefingSujet = (sujet) => {
  const aff = sujet.affinity || {};
  const tier = briefingTier(sujet.project_score);

  const row = h(
    "li",
    { class: "briefing-sujet", "data-tier": tier },
    h(
      "div",
      { class: "briefing-sujet__rank" },
      String(sujet.project_rank).padStart(2, "0"),
    ),
    // Score PM (gros) + global score (petit en dessous)
    h(
      "div",
      { class: "briefing-sujet__scores" },
      h(
        "div",
        { class: "briefing-sujet__score-pm" },
        h("span", { class: "briefing-sujet__score-value" }, String(sujet.project_score)),
        h("span", { class: "briefing-sujet__score-label" }, "PM"),
      ),
      h(
        "div",
        { class: "briefing-sujet__score-global" },
        `global ${sujet.global_score}`,
      ),
    ),
    // Title + signaux + affinity badge
    h(
      "div",
      { class: "briefing-sujet__body" },
      h("h3", { class: "briefing-sujet__title" }, sujet.title),
      h(
        "div",
        { class: "briefing-sujet__meta" },
        h(
          "span",
          { class: "briefing-sujet__theme" },
          sujet.theme || "—",
        ),
        renderOriginBadge(sujet.source_origin),
        renderAffinityBadge(aff),
      ),
    ),
    // Chevron expand
    h(
      "button",
      { class: "briefing-sujet__chevron", "aria-label": "Voir le détail" },
      "▾",
    ),
    // Détail expand
    renderBriefingDetail(sujet, aff),
  );

  row.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    row.classList.toggle("is-expanded");
  });

  return row;
};

const ORIGIN_LABELS = {
  msn: { label: "MSN", title: "Repéré dans le flux MSN (signal d'engagement)" },
  discover: { label: "Discover", title: "Repéré dans Google Discover, catégorie alignée avec le projet" },
  gnews: { label: "Actu", title: "Repéré dans Google Actualités, mot-clé thématique du projet" },
};

const renderOriginBadge = (origin) => {
  const meta = ORIGIN_LABELS[origin] || ORIGIN_LABELS.msn;
  return h(
    "span",
    {
      class: `briefing-sujet__origin is-${origin || "msn"}`,
      title: meta.title,
    },
    meta.label,
  );
};

const renderAffinityBadge = (aff) => {
  if (!aff || !aff.match_count) {
    return h(
      "span",
      { class: "briefing-sujet__affinity is-none" },
      "0 article historique",
    );
  }
  const tier =
    aff.score >= 70
      ? "is-success"
      : aff.score >= 40
        ? "is-warning"
        : "is-neutral";
  return h(
    "span",
    { class: `briefing-sujet__affinity ${tier}` },
    h("strong", {}, String(aff.match_count)),
    ` articles · `,
    h("strong", {}, formatNumber(aff.total_clicks)),
    ` clicks cumulés`,
  );
};

const renderBriefingDetail = (sujet, aff) => {
  const detail = h("div", { class: "briefing-sujet__detail" });

  // Rationale du sujet (signal global)
  if (sujet.rationale) {
    detail.appendChild(
      h(
        "p",
        { class: "briefing-sujet__rationale" },
        sujet.rationale,
      ),
    );
  }

  // Signaux globaux (DISCOVER · TRENDS · WIKI · MSN · X)
  if (sujet.global_signals?.length) {
    const sigs = h("div", { class: "briefing-sujet__signals" });
    for (const s of sujet.global_signals) {
      sigs.appendChild(
        h(
          "span",
          { class: `briefing-sujet__signal`, "data-source": s.source },
          h("span", { class: "briefing-sujet__signal-label" }, s.label),
          " ",
          h("span", { class: "briefing-sujet__signal-value" }, s.value),
        ),
      );
    }
    detail.appendChild(sigs);
  }

  // Titre proposé Paris Match (généré par Claude dans le style du média)
  if (sujet.proposed_title) {
    detail.appendChild(
      h(
        "div",
        { class: "briefing-sujet__proposed" },
        h(
          "div",
          { class: "briefing-sujet__proposed-head" },
          h("strong", {}, "Titre proposé"),
          h(
            "span",
            { class: "briefing-sujet__proposed-tag" },
            "✦ généré dans le style du média",
          ),
        ),
        h("p", { class: "briefing-sujet__proposed-title" }, sujet.proposed_title),
      ),
    );
  }

  // Top 3 contenus historiques similaires
  if (aff.top_matches?.length) {
    const block = h(
      "div",
      { class: "briefing-sujet__history" },
      h(
        "div",
        { class: "briefing-sujet__history-head" },
        h("strong", {}, `Tu as déjà cartonné sur des sujets similaires :`),
      ),
      h(
        "ul",
        { class: "briefing-sujet__history-list" },
        ...aff.top_matches.map((m) =>
          h(
            "li",
            { class: "briefing-sujet__history-item" },
            h(
              "span",
              { class: "briefing-sujet__history-sim" },
              `${(m.similarity * 100).toFixed(0)}%`,
            ),
            h(
              "div",
              { class: "briefing-sujet__history-body" },
              h(
                "a",
                {
                  class: "briefing-sujet__history-title",
                  href: m.url,
                  target: "_blank",
                  rel: "noopener noreferrer",
                },
                truncate(m.title || urlToReadable(m.url), 110),
              ),
              h(
                "span",
                { class: "briefing-sujet__history-clicks" },
                `${formatNumber(m.clicks)} clicks Discover`,
              ),
            ),
          ),
        ),
      ),
    );
    detail.appendChild(block);
  } else if (!aff.match_count) {
    detail.appendChild(
      h(
        "p",
        { class: "briefing-sujet__no-history" },
        "Aucun contenu historique vraiment similaire — c'est un sujet nouveau pour ce site.",
      ),
    );
  }

  // Sources externes : la 1re est l'article d'origine (d'où vient le titre
  // du sujet), les suivantes sont les sources qui traitent le même sujet.
  if (sujet.external_sources?.length) {
    detail.appendChild(
      h(
        "div",
        { class: "briefing-sujet__sources" },
        h(
          "div",
          { class: "briefing-sujet__sources-head" },
          h("strong", {}, "Sources externes pour aider à rédiger"),
        ),
        h(
          "ul",
          { class: "briefing-sujet__sources-list" },
          ...sujet.external_sources.map((s) => {
            const isOrigin = s.is_source_origin === true;
            const publisherLabel =
              s.publisher ||
              (s.source === "gnews"
                ? "Google News"
                : s.source === "msn"
                  ? "MSN"
                  : "Discover");
            return h(
              "li",
              {
                class:
                  "briefing-sujet__source-item" +
                  (isOrigin ? " is-source-origin" : ""),
              },
              isOrigin
                ? h(
                    "span",
                    { class: "briefing-sujet__source-origin-tag" },
                    "Origine",
                  )
                : null,
              h(
                "span",
                {
                  class: "briefing-sujet__source-publisher",
                  "data-kind": s.source,
                },
                publisherLabel,
              ),
              h(
                "a",
                {
                  class: "briefing-sujet__source-title",
                  href: s.url,
                  target: "_blank",
                  rel: "noopener noreferrer",
                },
                truncate(s.title, 130),
              ),
            );
          }),
        ),
      ),
    );
  }

  return detail;
};

/* ----- Wire des onglets secondaires ----- */

const wireSecondaryTabs = () => {
  const tabs = document.querySelectorAll(".project-secondary__tab");
  const panels = document.querySelectorAll(".project-secondary__panel");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const key = tab.dataset.tab;
      tabs.forEach((t) => t.classList.toggle("is-active", t === tab));
      panels.forEach((p) =>
        p.classList.toggle("is-active", p.dataset.panel === key),
      );
    });
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
