/* ===================================================================
   Reporter view — rendering + interactions
   =================================================================== */

import { myTopics, reporterMe } from "./data.js";
import {
  h,
  renderScore,
  renderSignal,
  arrowSvg,
  sparkSvg,
} from "./utils.js";

const stateLabel = {
  todo: "À traiter",
  doing: "En cours",
  done: "Traité",
};

const nextState = (cur) => {
  const seq = ["todo", "doing", "done"];
  return seq[(seq.indexOf(cur) + 1) % seq.length];
};

const renderMyTopic = (topic) => {
  const node = h(
    "li",
    {
      class: "mytopic",
      "data-id": topic.id,
      "data-state": topic.state,
    },
    h(
      "div",
      { class: "mytopic__score" },
      renderScore(topic.score, { size: "lg", label: "Signal" }),
    ),
    h(
      "div",
      { class: "mytopic__body" },
      h("span", { class: "mytopic__theme" }, topic.theme),
      h("h3", { class: "mytopic__title" }, topic.title),
      h(
        "div",
        { class: "mytopic__why" },
        h("span", { class: "mytopic__why-icon" }, sparkSvg()),
        h(
          "div",
          {},
          h("strong", {}, topic.why.lead),
          ". ",
          topic.why.stats,
          ".",
        ),
      ),
      h(
        "div",
        { class: "mytopic__signals" },
        ...topic.signals.map((s) => renderSignal(s)),
      ),
      topic.refs.length
        ? h(
            "div",
            { class: "mytopic__refs" },
            h("span", { class: "mytopic__refs-label" }, "Articles de référence"),
            ...topic.refs.map((r) =>
              h(
                "a",
                { class: "mytopic__ref", href: "#" },
                h("span", { class: "mytopic__ref-arrow" }, arrowSvg()),
                h("span", {}, r),
              ),
            ),
          )
        : null,
    ),
    h(
      "div",
      { class: "mytopic__aside" },
      h(
        "div",
        { class: "mytopic__status-stack" },
        renderStatusChip(topic, node => updateState(node, topic)),
        h(
          "span",
          { class: "mytopic__deadline" },
          h("span", { class: "mytopic__deadline-dot" }),
          topic.deadline,
        ),
      ),
    ),
  );
  return node;
};

const renderStatusChip = (topic, onToggle) => {
  const chip = h(
    "button",
    {
      class: "status-chip",
      "data-state": topic.state,
      onClick: (e) => {
        e.stopPropagation();
        topic.state = nextState(topic.state);
        const newChip = renderStatusChip(topic, onToggle);
        chip.replaceWith(newChip);
        chip.closest(".mytopic").setAttribute("data-state", topic.state);
        refreshCounts();
      },
    },
    h("span", { class: "status-chip__dot" }),
    stateLabel[topic.state],
  );
  return chip;
};

const updateState = (node, topic) => {
  node.setAttribute("data-state", topic.state);
};

/* ----- Counts ----- */

const refreshCounts = () => {
  const todo = myTopics.filter((t) => t.state === "todo").length;
  const doing = myTopics.filter((t) => t.state === "doing").length;
  const done = myTopics.filter((t) => t.state === "done").length;
  const high = myTopics.filter((t) => t.score >= 70).length;
  const el = document.querySelector("#stat-todo");
  if (el) el.textContent = String(todo + doing);
  const elHigh = document.querySelector("#stat-high");
  if (elHigh) elHigh.textContent = String(high);
  const elDone = document.querySelector("#stat-done");
  if (elDone) elDone.textContent = String(done);

  const doneBlock = document.querySelector("#done-block");
  if (doneBlock) {
    doneBlock.style.display = done === myTopics.length ? "block" : "none";
  }
};

/* ----- Mount ----- */

const mount = () => {
  document.querySelector("#greeting-name").textContent = reporterMe.name.split(" ")[0];

  const list = document.querySelector("#mytopics-list");
  for (const t of myTopics) list.appendChild(renderMyTopic(t));

  refreshCounts();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
