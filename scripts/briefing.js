/* ===================================================================
   Daily Briefing — rendering + interactions
   ===================================================================

   Les sujets viennent désormais du backend (data/sujets/latest.json).
   Le pool de rédacteurs reste mock le temps que le byline mapper
   Phase 1 produise data/byline/me.json.
*/

import { tierFromScore, tierLabel } from "./data.js";
import { loadSujets, formatFreshness, formatLongDate } from "./api.js";
import {
  h,
  renderScore,
  renderSignal,
  renderReporter,
  renderTierDivider,
  chevronSvg,
} from "./utils.js";

/* ----- Sujet row (liste) ----- */

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
    h("div", { class: "sujet__reporter" }, renderReporter(sujet.reporter, { showStats: true })),
    h("button", { class: "sujet__chevron", "aria-label": "Voir détail" }, chevronSvg()),
    renderDetail(sujet),
  );

  row.addEventListener("click", (e) => {
    if (e.target.closest("button")?.classList.contains("btn")) return;
    row.classList.toggle("is-expanded");
  });

  return row;
};

/* ----- Detail (collapsed) ----- */

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

  const reporterStack = [sujet.reporter, ...sujet.altReporters].map((rep, idx) =>
    h(
      "div",
      {
        class: `detail-reporter-item${idx === 0 ? " is-recommended" : ""}`,
      },
      renderReporter(rep),
      h("span", { class: "detail-reporter-item__score" }, String(rep.themeScore)),
      h(
        "span",
        { class: "detail-reporter-item__choose" },
        idx === 0 ? "Recommandé" : "Assigner",
      ),
    ),
  );

  const refs = sujet.refs?.length
    ? h(
        "div",
        { class: "detail-sources", style: "margin-top: 20px" },
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
      { class: "detail-col" },
      h("span", { class: "detail-col__label" }, "Rédacteurs possibles"),
      h("div", { class: "detail-reporter-stack" }, ...reporterStack),
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
            action("reassign", sujet);
          },
        },
        "Réassigner",
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
    reassign: "Réassigner — sélecteur à venir",
    reject: "Rejeté",
  };
  toast(`${labels[kind]} · ${sujet.title.slice(0, 60)}${sujet.title.length > 60 ? "…" : ""}`);
};

/* ----- Toast ----- */

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

/* ----- States: loading / error ----- */

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

/* ----- Counts UI helpers ----- */

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

/* ----- Mount ----- */

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

  const { sujets, generatedAt } = data;
  list.innerHTML = "";

  const sorted = [...sujets].sort((a, b) => b.score - a.score);
  const buckets = { high: [], medium: [], low: [] };
  for (const s of sorted) buckets[tierFromScore(s.score)].push(s);

  for (const tier of ["high", "medium", "low"]) {
    if (buckets[tier].length === 0) continue;
    list.appendChild(renderTierDivider(tierLabel[tier], buckets[tier].length));
    for (const s of buckets[tier]) list.appendChild(renderSujet(s));
  }

  setCounts(sorted);
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
