/* ============================================================
   EDITORIAL SIGNAL — Shell partagé (topnav)
   Rend la barre de navigation cockpit-pro dans #shell-mount.
   Chaque page passe son activeKey : 'flux', 'sources', 'categories',
   'evolution', 'projets'.
   ============================================================ */

const NAV = [
  { key: "flux", label: "Flux global", href: "index.html" },
  { key: "sources", label: "Sources", href: "tendances.html" },
  { key: "categories", label: "Catégories", href: "categories.html" },
  { key: "evolution", label: "Évolution", href: "evolution.html" },
  { key: "projets", label: "Projets", href: "projects.html" },
];

const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
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

const svg = (paths, w = 15, hp = 15) => {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "2");
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("width", String(w));
  s.setAttribute("height", String(hp));
  s.innerHTML = paths;
  return s;
};

const searchIcon = () => svg('<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>', 15, 15);

const renderShell = (activeKey, opts = {}) => {
  const mount = document.getElementById("shell-mount");
  if (!mount) return;

  const nav = h(
    "nav",
    { class: "topnav" },
    h(
      "div",
      { class: "topnav-inner" },
      h(
        "a",
        { class: "cp-brand", href: "index.html", style: "text-decoration:none" },
        h("div", { class: "brand-mark" }, h("span", { class: "pulse" })),
        h(
          "div",
          { class: "brand-text" },
          h("span", { class: "brand-name" }, "EDITORIAL SIGNAL"),
          h("span", { class: "brand-sub" }, "The Black Room"),
        ),
      ),
      h(
        "div",
        { class: "nav-links" },
        ...NAV.map((l) =>
          h(
            "a",
            { class: "nav-link" + (l.key === activeKey ? " active" : ""), href: l.href },
            l.label,
          ),
        ),
      ),
      h("div", { class: "nav-spacer" }),
      // Search optionnelle (off par défaut sur les pages secondaires pour
      // éviter de dupliquer la recherche page-specific de tendances/categories)
      opts.search === false
        ? null
        : h(
            "div",
            { class: "nav-search" },
            searchIcon(),
            h("input", {
              placeholder: opts.searchPlaceholder || "Rechercher…",
              type: "search",
              oninput: opts.onSearch || (() => {}),
            }),
          ),
      h(
        "div",
        { class: "user-chip" },
        h(
          "div",
          { class: "user-meta" },
          h("div", { class: "user-role" }, "Rédac chef"),
          h("div", { class: "user-name" }, "Clément P."),
        ),
        h(
          "button",
          {
            class: "cp-avatar",
            "data-auth-logout": "",
            title: "Cliquer pour se déconnecter",
          },
          "CP",
        ),
      ),
    ),
  );

  mount.innerHTML = "";
  mount.appendChild(nav);
};

// Auto-mount si data-shell-active est sur le mount
const autoMount = () => {
  const mount = document.getElementById("shell-mount");
  if (mount && mount.dataset.shellActive) {
    renderShell(mount.dataset.shellActive, {
      search: mount.dataset.shellSearch !== "false",
    });
  }
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", autoMount);
} else {
  autoMount();
}

export { renderShell };
