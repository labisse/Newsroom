/* ===================================================================
   Page Projets — design Claude (encre éditoriale élevée).
   Vanilla JS, mount dans #cp-root.
   Carte par projet + modal "Nouveau projet" + toast feedback.
   =================================================================== */

import { h } from "./utils.js";

const PROJECTS_URL = "/data/projects/index.json";

/* ---------- DOM helper SVG ---------- */
const svgEl = (path, attrs = {}) => {
  const NS = "http://www.w3.org/2000/svg";
  const node = document.createElementNS(NS, "svg");
  const base = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": "2",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    width: "16",
    height: "16",
  };
  for (const [k, v] of Object.entries({ ...base, ...attrs })) {
    node.setAttribute(k, v);
  }
  node.innerHTML = path;
  return node;
};

const Ic = {
  plus: (a) => svgEl(`<path d="M12 5v14M5 12h14"/>`, { "stroke-width": "2.4", ...a }),
  arrow: (a) => svgEl(`<path d="M5 12h14M13 6l6 6-6 6"/>`, a),
  link: (a) => svgEl(`<path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 0 0-7.07-7.07l-1 1"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3a5 5 0 0 0 7.07 7.07l1-1"/>`, a),
  check: (a) => svgEl(`<path d="M20 6 9 17l-5-5"/>`, a),
};

/* ---------- palette accents pour favicon ---------- */
const ACCENT_GRADIENTS = {
  pink: "linear-gradient(135deg, #f472b6, #a855f7)",
  blue: "linear-gradient(135deg, #60a5fa, #6366f1)",
  emerald: "linear-gradient(135deg, #34d399, #06b6d4)",
  amber: "linear-gradient(135deg, #fbbf24, #f97316)",
  purple: "linear-gradient(135deg, #a855f7, #6366f1)",
  indigo: "linear-gradient(135deg, #6366f1, #8b5cf6)",
};
const ACCENT_LINE = {
  pink: "#f472b6",
  blue: "#60a5fa",
  emerald: "#34d399",
  amber: "#fbbf24",
  purple: "#a855f7",
  indigo: "#6366f1",
};
const ACCENT_KEYS = Object.keys(ACCENT_GRADIENTS);

const accentForIndex = (i) => ACCENT_KEYS[i % ACCENT_KEYS.length];

const monogram = (name) => {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0] || "")
    .join("")
    .toUpperCase();
};

/* ---------- card ---------- */
const renderCard = (project, accent, onConnect) => {
  const connected = !!project.gsc_connected;
  const themes = (project.themes || []).slice(0, 6);
  const slug = encodeURIComponent(project.slug || "");
  const fluxLabel = connected ? "personnalisé" : "générique";

  const card = h("li", { class: "pj-card" });
  card.style.setProperty("--pj-accent", ACCENT_LINE[accent] || "var(--brand-2)");

  // head : favicon + GSC badge
  const fav = h(
    "div",
    { class: "pj-fav" },
    document.createTextNode(monogram(project.name || "?")),
  );
  fav.style.background = ACCENT_GRADIENTS[accent] || "var(--brand-grad)";
  const badge = h(
    "span",
    { class: "pj-gsc " + (connected ? "is-connected" : "is-pending") },
    h("span", { class: "pj-gsc-dot" }),
    document.createTextNode(connected ? "GSC connecté" : "GSC en attente"),
  );
  card.appendChild(h("div", { class: "pj-card-head" }, fav, badge));

  // name + domain
  card.appendChild(h("div", { class: "pj-name" }, project.name));
  if (project.domain) {
    const dom = h(
      "a",
      {
        class: "pj-domain",
        href: `https://${project.domain}`,
        target: "_blank",
        rel: "noopener",
      },
      project.domain,
    );
    dom.addEventListener("click", (e) => e.stopPropagation());
    card.appendChild(dom);
  }

  // tagline
  if (project.tagline) {
    card.appendChild(h("div", { class: "pj-desc" }, project.tagline));
  }

  // themes
  if (themes.length) {
    const tagsWrap = h("div", { class: "pj-tags" });
    for (const t of themes) {
      tagsWrap.appendChild(h("span", { class: "pj-tag" }, t));
    }
    card.appendChild(tagsWrap);
  }

  // meta flux
  const dotColor = connected ? "var(--up)" : "var(--warm)";
  const fluxDot = h("span", { class: "d" });
  fluxDot.style.background = dotColor;
  card.appendChild(
    h(
      "div",
      { class: "pj-meta" },
      h(
        "span",
        { class: "flux" },
        fluxDot,
        document.createTextNode(`Flux Discover : ${fluxLabel}`),
      ),
    ),
  );

  // footer : open + connect
  const open = h(
    "a",
    { class: "pj-open", href: `project.html?slug=${slug}` },
    document.createTextNode("Ouvrir le projet "),
    Ic.arrow(),
  );

  let btn;
  if (connected) {
    btn = h(
      "button",
      { class: "pj-btn-connect is-on", type: "button" },
      Ic.check(),
      document.createTextNode("Connecté"),
    );
  } else {
    btn = h(
      "button",
      { class: "pj-btn-connect", type: "button" },
      Ic.link(),
      document.createTextNode("Connecter GSC"),
    );
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      onConnect(project);
    });
  }

  card.appendChild(h("div", { class: "pj-foot" }, open, btn));
  return card;
};

const renderAddCard = (onAdd) => {
  const card = h(
    "li",
    {},
    h(
      "button",
      { class: "pj-addcard", type: "button" },
      h("span", { class: "plus" }, Ic.plus()),
      h("span", { class: "t" }, "Ajouter un site"),
      h("span", { class: "s" }, "Connecter un nouveau domaine"),
    ),
  );
  card.querySelector("button").addEventListener("click", onAdd);
  return card;
};

/* ---------- modal ---------- */
const openModal = ({ onCreate }) => {
  const scrim = h("div", { class: "pj-scrim" });
  const modal = h("div", { class: "pj-modal" });
  modal.addEventListener("click", (e) => e.stopPropagation());

  const head = h(
    "div",
    { class: "pj-modal-head" },
    h(
      "div",
      { class: "pj-eyebrow" },
      h("span", { class: "ln" }),
      document.createTextNode("Nouveau projet"),
    ),
    h("h3", {}, "Ajouter un site"),
    h(
      "p",
      {},
      "Connectez un site pour générer son flux Discover personnalisé une fois la Search Console reliée.",
    ),
  );

  const inputs = {};
  const mkField = (key, label, placeholder, hint) => {
    const input = h("input", {
      type: "text",
      placeholder,
      autocomplete: "off",
    });
    inputs[key] = input;
    const field = h(
      "div",
      { class: "pj-field" },
      h("label", {}, label),
      input,
    );
    if (hint) field.appendChild(h("div", { class: "hint" }, hint));
    return field;
  };

  const body = h(
    "div",
    { class: "pj-modal-body" },
    mkField("name", "Nom du site", "ex : Le Parisien"),
    mkField("domain", "Domaine", "ex : leparisien.fr"),
    mkField("desc", "Description", "Ligne éditoriale du site"),
    mkField(
      "tags",
      "Univers éditoriaux",
      "Actualité, Sport, Faits divers…",
      "Séparez par des virgules — sert à filtrer les opportunités du flux.",
    ),
  );

  const cancelBtn = h(
    "button",
    { class: "pj-btn-ghost", type: "button" },
    "Annuler",
  );
  const createBtn = h(
    "button",
    { class: "pj-btn-primary", type: "button" },
    Ic.check(),
    document.createTextNode("Créer le projet"),
  );
  createBtn.disabled = true;
  const foot = h("div", { class: "pj-modal-foot" }, cancelBtn, createBtn);

  modal.appendChild(head);
  modal.appendChild(body);
  modal.appendChild(foot);
  scrim.appendChild(modal);

  const validate = () => {
    createBtn.disabled = !(
      inputs.name.value.trim().length > 0 &&
      inputs.domain.value.trim().length > 0
    );
  };
  for (const inp of Object.values(inputs)) {
    inp.addEventListener("input", validate);
  }

  const close = () => {
    scrim.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (e) => {
    if (e.key === "Escape") close();
  };
  scrim.addEventListener("click", close);
  cancelBtn.addEventListener("click", close);
  createBtn.addEventListener("click", () => {
    if (createBtn.disabled) return;
    onCreate({
      name: inputs.name.value.trim(),
      domain: inputs.domain.value
        .trim()
        .replace(/^https?:\/\//, "")
        .replace(/\/$/, ""),
      tagline:
        inputs.desc.value.trim() ||
        "Nouveau site — flux Discover en cours de configuration.",
      themes: inputs.tags.value
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, 6),
    });
    close();
  });
  document.addEventListener("keydown", onKey);

  document.body.appendChild(scrim);
  inputs.name.focus();
};

/* ---------- toast ---------- */
const showToast = (msg) => {
  const old = document.querySelector(".pj-toast");
  if (old) old.remove();
  const t = h(
    "div",
    { class: "pj-toast" },
    h("span", { class: "ic" }, Ic.check()),
    document.createTextNode(msg),
  );
  document.body.appendChild(t);
  clearTimeout(window.__pjToast);
  window.__pjToast = setTimeout(() => t.remove(), 2800);
};

/* ---------- render ---------- */
const mount = async () => {
  const root = document.getElementById("cp-root");
  if (!root) return;

  // hero (rendered upfront, list filled after fetch)
  const renderHero = (onNew) => {
    const btn = h(
      "button",
      { class: "pj-btn-new", type: "button" },
      Ic.plus({ width: "16", height: "16" }),
      document.createTextNode("Nouveau projet"),
    );
    btn.addEventListener("click", onNew);
    return h(
      "section",
      { class: "pj-hero" },
      h(
        "div",
        { class: "pj-left" },
        h(
          "div",
          { class: "pj-eyebrow" },
          h("span", { class: "ln" }),
          document.createTextNode("Sites configurés"),
        ),
        h(
          "h1",
          {},
          document.createTextNode("Projets "),
          h("span", { class: "accent" }, "par site"),
        ),
        h(
          "p",
          {},
          "Chaque projet aura son flux Discover personnalisé une fois la connexion Google Search Console établie. Combine signaux externes et historique d’audience pour anticiper les sujets à fort potentiel.",
        ),
      ),
      btn,
    );
  };

  let projects = [];

  const handleNew = () => {
    openModal({
      onCreate: (data) => {
        projects = [
          ...projects,
          {
            slug: `local-${Date.now()}`,
            ...data,
            gsc_connected: false,
            __local: true,
          },
        ];
        repaint();
        showToast(`${data.name} ajouté à vos projets`);
      },
    });
  };

  const handleConnect = (project) => {
    projects = projects.map((p) =>
      p.slug === project.slug ? { ...p, gsc_connected: true } : p,
    );
    repaint();
    showToast(`${project.name} · Search Console connectée`);
  };

  const repaint = () => {
    root.innerHTML = "";
    root.appendChild(renderHero(handleNew));
    root.appendChild(h("hr", { class: "pj-divider" }));

    const connected = projects.filter((p) => p.gsc_connected).length;
    const total = projects.length;
    const countLabel = `${total} projet${total > 1 ? "s" : ""} · ${connected} connecté${connected > 1 ? "s" : ""} à GSC`;

    root.appendChild(
      h(
        "div",
        { class: "pj-listhead" },
        h("h2", {}, "Vos sites"),
        h("span", { class: "count" }, countLabel),
      ),
    );

    const grid = h("ul", { class: "pj-grid" });
    if (projects.length === 0) {
      const empty = h(
        "li",
        {
          style:
            "grid-column:1/-1;padding:32px;text-align:center;color:var(--fg-muted);",
        },
        h("strong", {}, "Aucun projet pour le moment."),
        h(
          "p",
          { style: "margin-top:6px;font-size:13px;" },
          "Crée ton premier projet pour brancher un site.",
        ),
      );
      grid.appendChild(empty);
    } else {
      projects.forEach((p, i) => {
        const accent = accentForIndex(i);
        grid.appendChild(renderCard(p, accent, handleConnect));
      });
    }
    grid.appendChild(renderAddCard(handleNew));
    root.appendChild(grid);
  };

  // initial render (hero only, while loading)
  root.appendChild(renderHero(handleNew));
  root.appendChild(h("hr", { class: "pj-divider" }));
  root.appendChild(
    h(
      "div",
      { class: "pj-listhead" },
      h("h2", {}, "Vos sites"),
      h("span", { class: "count" }, "Chargement…"),
    ),
  );

  try {
    const res = await fetch(PROJECTS_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    projects = payload.projects || [];
  } catch {
    projects = [];
    repaint();
    showToast("Impossible de charger data/projects/index.json");
    return;
  }
  repaint();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
