(() => {
  "use strict";

  const root = document.getElementById("amx-data-structure-v1");
  if (!root || root.dataset.initialized === "true") return;
  root.dataset.initialized = "true";

  const parseColor = (value) => {
    const match = String(value).match(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)(?:[, /]+([\d.]+))?\)/i);
    if (!match) return null;
    return {
      r: Number(match[1]),
      g: Number(match[2]),
      b: Number(match[3]),
      a: match[4] === undefined ? 1 : Number(match[4]),
    };
  };

  let themeHost = null;
  const applyTheme = (theme) => {
    root.dataset.theme = theme;
    if (themeHost) themeHost.dataset.amxStructureTheme = theme;
  };

  const resolveTheme = () => {
    let element = root;
    let color = null;
    while (element && (!color || color.a === 0)) {
      color = parseColor(getComputedStyle(element).backgroundColor);
      element = element.parentElement;
    }
    if (!color || color.a === 0) {
      applyTheme(matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      return;
    }
    const channels = [color.r, color.g, color.b].map((channel) => {
      const normalized = channel / 255;
      return normalized <= 0.04045
        ? normalized / 12.92
        : Math.pow((normalized + 0.055) / 1.055, 2.4);
    });
    const luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    applyTheme(luminance < 0.32 ? "dark" : "light");
  };

  themeHost = root.closest(".stApp") || root.parentElement;
  resolveTheme();
  if (themeHost) {
    const themeObserver = new MutationObserver(resolveTheme);
    themeObserver.observe(themeHost, { attributes: true, attributeFilter: ["class", "style"] });
  }

  const synchronizeDetails = (details) => {
    const summary = details.querySelector(":scope > summary");
    if (summary) summary.setAttribute("aria-expanded", details.open ? "true" : "false");
    const card = details.closest(".info-card");
    if (card) card.classList.toggle("is-open", details.open);
  };

  root.querySelectorAll("details.card-details").forEach(synchronizeDetails);
  root.addEventListener("toggle", (event) => {
    const details = event.target;
    if (details instanceof HTMLDetailsElement && details.classList.contains("card-details")) {
      synchronizeDetails(details);
    }
  }, true);

  root.addEventListener("click", (event) => {
    const close = event.target.closest("[data-action='close-details']");
    if (close && root.contains(close)) {
      const details = close.closest("details");
      const summary = details ? details.querySelector(":scope > summary") : null;
      if (details) {
        details.open = false;
        synchronizeDetails(details);
      }
      if (summary) summary.focus();
      return;
    }

    const node = event.target.closest("button.gold-node[data-table]");
    if (node && root.contains(node)) selectTable(node.dataset.table);
  });

  root.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const active = root.ownerDocument.activeElement;
    const details = active ? active.closest("details.card-details[open]") : null;
    if (!details || !root.contains(details)) return;
    const summary = details.querySelector(":scope > summary");
    details.open = false;
    synchronizeDetails(details);
    if (summary) summary.focus();
  });

  const techToggle = root.querySelector("#tech-toggle");
  techToggle.addEventListener("click", () => {
    const active = techToggle.getAttribute("aria-pressed") !== "true";
    techToggle.setAttribute("aria-pressed", active ? "true" : "false");
    root.dataset.technical = active ? "true" : "false";
    techToggle.textContent = active ? "Ocultar nombres técnicos" : "Ver nombres técnicos";
    tableSelector.querySelectorAll("option[value]").forEach((option) => {
      option.textContent = active
        ? `${option.dataset.businessLabel} · ${option.dataset.technicalName}`
        : option.dataset.businessLabel;
    });
    scheduleDraw();
  });

  const goldDetail = root.querySelector("#gold-detail");
  const tableSelector = root.querySelector("#table-selector");
  const factSelector = root.querySelector("#fact-selector");
  const factNode = root.querySelector("#gold-fact-node");
  const goldMap = root.querySelector(".gold-map");
  const svgElement = (name, attributes) => {
    const element = root.ownerDocument.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    return element;
  };
  const goldSvgHost = goldMap;
  const goldSvg = svgElement("svg", {
    class: "gold-svg",
    "aria-hidden": "true",
    focusable: "false",
  });
  const definitions = svgElement("defs", {});
  const relationMarker = svgElement("marker", {
    id: "gold-relation-arrowhead",
    markerWidth: "9",
    markerHeight: "7",
    refX: "8",
    refY: "3.5",
    orient: "auto",
  });
  relationMarker.append(svgElement("path", {
    class: "relation-arrowhead",
    d: "M0,0 L9,3.5 L0,7 Z",
  }));
  const flowMarker = svgElement("marker", {
    id: "gold-flow-arrowhead",
    markerWidth: "9",
    markerHeight: "7",
    refX: "8",
    refY: "3.5",
    orient: "auto",
  });
  flowMarker.append(svgElement("path", {
    class: "flow-arrowhead",
    d: "M0,0 L9,3.5 L0,7 Z",
  }));
  definitions.append(relationMarker, flowMarker);
  goldSvg.append(definitions);
  goldSvgHost.append(goldSvg);
  const edgeRecords = Array.from(root.querySelectorAll(".gold-edge-record"));
  const consumerRecords = Array.from(root.querySelectorAll(".gold-consumer-record"));
  const semanticNode = root.querySelector("#semantic-node");
  const analyticsNode = root.querySelector("#analytics-node");
  const pagesNode = root.querySelector("#pages-node");

  const splitMetadata = (value) => value ? value.split(" | ").filter(Boolean) : [];

  const updateConsumerNode = (node, values, singular, plural) => {
    const label = values.length === 1 ? singular : plural;
    const description = values.length ? `${values.length} ${label}` : "Sin relación declarada para este hecho";
    node.querySelector("span").textContent = description;
    node.classList.toggle("is-empty", values.length === 0);
    node.title = values.join(" · ");
  };

  function selectTable(tableName) {
    if (!tableName) return;
    const template = Array.from(root.querySelectorAll("template[data-table-template]"))
      .find((item) => item.dataset.tableTemplate === tableName);
    if (!template) return;
    goldDetail.replaceChildren(template.content.cloneNode(true));
    root.querySelectorAll("button.gold-node[data-table]").forEach((node) => {
      node.setAttribute("aria-pressed", node.dataset.table === tableName ? "true" : "false");
    });
    tableSelector.value = tableName;
  }

  tableSelector.addEventListener("change", () => selectTable(tableSelector.value));

  const activeParentTables = () => edgeRecords
    .filter((record) => record.dataset.child === factSelector.value)
    .map((record) => record.dataset.parent);

  const updateFact = () => {
    const option = factSelector.selectedOptions[0];
    const tableName = factSelector.value;
    factNode.dataset.table = tableName;
    factNode.querySelector(".business-label").textContent = option.dataset.label;
    factNode.querySelector(".technical-label").textContent = tableName;
    const parents = new Set(activeParentTables());
    root.querySelectorAll(".dimension-node").forEach((node) => {
      node.classList.toggle("is-related", parents.has(node.dataset.table));
      node.classList.toggle("is-muted", !parents.has(node.dataset.table));
    });
    const consumerRecord = consumerRecords.find((record) => record.dataset.table === tableName);
    const views = splitMetadata(consumerRecord ? consumerRecord.dataset.views : "");
    const analytics = splitMetadata(consumerRecord ? consumerRecord.dataset.analytics : "");
    const pages = splitMetadata(consumerRecord ? consumerRecord.dataset.pages : "");
    updateConsumerNode(semanticNode, views, "vista conectada", "vistas conectadas");
    updateConsumerNode(analyticsNode, analytics, "resultado conectado", "resultados conectados");
    updateConsumerNode(pagesNode, pages, "página conectada", "páginas conectadas");
    selectTable(tableName);
    scheduleDraw();
  };

  factSelector.addEventListener("change", updateFact);

  const pointFor = (element, side, mapRect) => {
    const rect = element.getBoundingClientRect();
    if (side === "right") return { x: rect.right - mapRect.left, y: rect.top + rect.height / 2 - mapRect.top };
    if (side === "left") return { x: rect.left - mapRect.left, y: rect.top + rect.height / 2 - mapRect.top };
    if (side === "bottom") return { x: rect.left + rect.width / 2 - mapRect.left, y: rect.bottom - mapRect.top };
    return { x: rect.left + rect.width / 2 - mapRect.left, y: rect.top - mapRect.top };
  };

  const drawConnection = (from, to, kind, label) => {
    if (!from || !to) return;
    const mapRect = goldMap.getBoundingClientRect();
    const horizontal = goldMap.clientWidth > 820;
    const start = pointFor(from, horizontal ? "right" : "bottom", mapRect);
    const end = pointFor(to, horizontal ? "left" : "top", mapRect);
    let d;
    if (horizontal) {
      const bend = Math.max(28, (end.x - start.x) * 0.48);
      d = `M ${start.x} ${start.y} C ${start.x + bend} ${start.y}, ${end.x - bend} ${end.y}, ${end.x} ${end.y}`;
    } else {
      const bend = Math.max(24, (end.y - start.y) * 0.48);
      d = `M ${start.x} ${start.y} C ${start.x} ${start.y + bend}, ${end.x} ${end.y - bend}, ${end.x} ${end.y}`;
    }
    const path = svgElement("path", {
      d,
      class: kind === "relation" ? "relation-path" : "flow-path",
      "data-testid": "gold-edge",
      "data-relation": label,
    });
    const title = svgElement("title", {});
    title.textContent = label;
    path.append(title);
    goldSvg.append(path);
  };

  let drawPending = false;
  function scheduleDraw() {
    if (drawPending) return;
    drawPending = true;
    requestAnimationFrame(() => {
      drawPending = false;
      goldSvg.querySelectorAll(".relation-path, .flow-path").forEach((path) => path.remove());
      const currentFact = factSelector.value;
      edgeRecords
        .filter((record) => record.dataset.child === currentFact)
        .forEach((record) => {
          const parent = Array.from(root.querySelectorAll(".dimension-node"))
            .find((node) => node.dataset.table === record.dataset.parent);
          drawConnection(parent, factNode, "relation", `${record.dataset.parent} → ${currentFact} · ${record.dataset.label}`);
        });
      if (!semanticNode.classList.contains("is-empty")) {
        drawConnection(factNode, semanticNode, "flow", "Hecho → vistas semánticas declaradas");
      }
      if (!analyticsNode.classList.contains("is-empty")) {
        drawConnection(factNode, analyticsNode, "flow", "Hecho → resultados analíticos declarados");
      }
      if (!pagesNode.classList.contains("is-empty")) {
        drawConnection(factNode, pagesNode, "flow", "Hecho → páginas consumidoras declaradas");
      }
    });
  }

  const mapObserver = new ResizeObserver(scheduleDraw);
  mapObserver.observe(goldMap);
  updateFact();
})();
