/* ===================================================================
   Shared rendering helpers
   =================================================================== */

import { tierFromScore } from "./data.js";

export const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("data-")) el.setAttribute(k, v);
    else if (k.startsWith("on") && typeof v === "function") {
      el.addEventListener(k.slice(2).toLowerCase(), v);
    } else if (k in el && typeof v !== "object") {
      el[k] = v;
    } else {
      el.setAttribute(k, v);
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return el;
};

/* ----- Score badge ----- */

export const renderScore = (value, { size = "md", label } = {}) => {
  const tier = tierFromScore(value);
  const cls = ["score"];
  if (size === "lg") cls.push("score--lg");
  if (size === "xs") cls.push("score--xs");
  const attrs = { class: cls.join(" "), "data-tier": tier };
  if (label) attrs["data-label"] = label;
  return h(
    "div",
    attrs,
    h("span", { class: "score__ring" }),
    h("span", { class: "score__value" }, String(value)),
  );
};

/* ----- Signal pill ----- */

export const renderSignal = (signal, { variant } = {}) => {
  const cls = ["signal"];
  if (variant === "hero") cls.push("signal--hero");
  return h(
    "div",
    { class: cls.join(" "), "data-source": signal.source },
    h("span", { class: "signal__dot" }),
    h("span", { class: "signal__label" }, signal.label),
    h("span", { class: "signal__value" }, signal.value),
  );
};

/* ----- Reporter chip ----- */

export const renderReporter = (reporter, { size, showStats } = {}) => {
  const cls = ["reporter"];
  if (size === "lg") cls.push("reporter--lg");
  return h(
    "div",
    { class: cls.join(" ") },
    h(
      "div",
      {
        class: "reporter__avatar",
        style: `--reporter-bg: ${reporter.avatarBg}`,
      },
      reporter.initials,
    ),
    h(
      "div",
      { class: "reporter__body" },
      h("span", { class: "reporter__name" }, reporter.name),
      h(
        "span",
        { class: "reporter__theme" },
        showStats
          ? h("strong", {}, String(reporter.themeScore))
          : null,
        reporter.theme,
      ),
    ),
  );
};

/* ----- Tier divider ----- */

export const renderTierDivider = (label, count) =>
  h(
    "div",
    { class: "tier-divider" },
    h("span", {}, label),
    h("span", { class: "tier-divider__line" }),
    h("span", {}, `${count} sujet${count > 1 ? "s" : ""}`),
  );

/* ----- Chevron icon ----- */

export const chevronSvg = () => {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("fill", "none");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", "M2.5 4.5L6 8L9.5 4.5");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.5");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.appendChild(path);
  return svg;
};

export const arrowSvg = () => {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("fill", "none");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", "M3 6h6m0 0L6.5 3.5M9 6L6.5 8.5");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.2");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.appendChild(path);
  return svg;
};

export const sparkSvg = () => {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("fill", "none");
  const path = document.createElementNS(ns, "path");
  path.setAttribute(
    "d",
    "M6 1.5L7 4.5L10 5.5L7 6.5L6 9.5L5 6.5L2 5.5L5 4.5L6 1.5Z",
  );
  path.setAttribute("fill", "currentColor");
  svg.appendChild(path);
  return svg;
};
