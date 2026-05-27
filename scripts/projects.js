/* ===================================================================
   Page Projets — liste des sites configurés.

   Chaque projet a (mock pour cette session) :
     - slug, name, domain, tagline, themes[], gsc_connected
   Cliquer ouvre project.html?slug=...
   =================================================================== */

import { h } from "./utils.js";

const PROJECTS_URL = "/data/projects/index.json";

const renderProjectCard = (project) => {
  const themes = (project.themes || []).slice(0, 5);
  return h(
    "li",
    { class: "project-card" },
    h(
      "a",
      {
        class: "project-card__link",
        href: `project.html?slug=${encodeURIComponent(project.slug)}`,
      },
      h(
        "span",
        {
          class: `project-card__status ${
            project.gsc_connected ? "is-connected" : "is-pending"
          }`,
        },
        project.gsc_connected ? "GSC connecté" : "GSC en attente",
      ),
      h(
        "div",
        { class: "project-card__head" },
        h("h3", { class: "project-card__name" }, project.name),
        h("span", { class: "project-card__domain" }, project.domain),
      ),
      project.tagline
        ? h("p", { class: "project-card__tagline" }, project.tagline)
        : null,
      themes.length
        ? h(
            "div",
            { class: "project-card__themes" },
            ...themes.map((t) =>
              h("span", { class: "project-card__theme" }, t),
            ),
          )
        : null,
      h(
        "div",
        { class: "project-card__cta" },
        h("span", {}, "Ouvrir le projet"),
        h("span", { class: "project-card__cta-arrow" }, "→"),
      ),
    ),
  );
};

const renderError = (grid, message) => {
  grid.innerHTML = "";
  grid.appendChild(
    h(
      "li",
      { class: "project-empty project-empty--error" },
      h("strong", {}, "Configuration introuvable."),
      h("p", {}, message),
    ),
  );
};

const showToast = (message) => {
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
  }, 3000);
};

const mount = async () => {
  const grid = document.querySelector("#projects-grid");
  const meta = document.querySelector("#projects-meta");

  let payload;
  try {
    const res = await fetch(PROJECTS_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload = await res.json();
  } catch {
    renderError(grid, "data/projects/index.json est manquant ou invalide.");
    meta.textContent = "—";
    return;
  }

  const projects = payload.projects || [];
  grid.innerHTML = "";

  if (projects.length === 0) {
    grid.appendChild(
      h(
        "li",
        { class: "project-empty" },
        h("strong", {}, "Aucun projet."),
        h("p", {}, "Crée ton premier projet pour brancher un site."),
      ),
    );
  } else {
    for (const project of projects) {
      grid.appendChild(renderProjectCard(project));
    }
  }

  const connected = projects.filter((p) => p.gsc_connected).length;
  const total = projects.length;
  meta.textContent =
    `${total} projet${total > 1 ? "s" : ""} · ${connected} connecté${connected > 1 ? "s" : ""} à GSC`;

  document.querySelector("#new-project-btn")?.addEventListener("click", () => {
    showToast(
      "Création de projet : à venir. Édite data/projects/index.json pour ajouter un site en attendant.",
    );
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
