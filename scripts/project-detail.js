/* ===================================================================
   Page projet individuel — lit ?slug= et affiche les infos.

   Placeholder pour cette session : pas encore de flux personnalisé,
   on attend la connexion GSC (voir project.html section "pending").
   =================================================================== */

import { h } from "./utils.js";

const PROJECTS_URL = "/data/projects/index.json";

const setText = (selector, value) => {
  const el = document.querySelector(selector);
  if (el) el.textContent = value;
};

const showError = (message) => {
  const main = document.querySelector("#project-main");
  const errorBox = document.querySelector("#project-error");
  if (!main || !errorBox) return;

  main.querySelector(".project-detail-hero")?.remove();
  main.querySelector(".project-pending")?.remove();
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

const mount = async () => {
  const params = new URLSearchParams(window.location.search);
  const slug = params.get("slug");

  if (!slug) {
    showError("Aucun slug fourni dans l'URL (project.html?slug=…).");
    return;
  }

  let payload;
  try {
    const res = await fetch(PROJECTS_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload = await res.json();
  } catch {
    showError("Impossible de charger data/projects/index.json.");
    return;
  }

  const project = (payload.projects || []).find((p) => p.slug === slug);
  if (!project) {
    showError(`Aucun projet ne correspond au slug "${slug}".`);
    return;
  }

  document.title = `${project.name} · Editorial Signal · The Black Room`;
  setText("#project-name", project.name);
  setText("#project-domain", project.domain || "");
  setText("#project-tagline", project.tagline || "");
  renderThemes(project.themes);
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
