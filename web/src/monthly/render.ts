import type { Claim, Issue, Source, Traffic } from "./model";
import { issueRoute } from "./model";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function link(text: string, href: string): HTMLAnchorElement {
  const node = el("a", text);
  node.href = href;
  return node;
}

function date(value: string): string {
  return new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function citation(id: string, sources: Source[]): HTMLElement {
  const index = sources.findIndex((source) => source.id === id);
  const source = sources[index];
  if (!source) throw new Error(`Fuente ausente: ${id}`);
  const node = link(`[${index + 1}]`, source.url);
  node.className = "citation";
  node.title = `${source.publisher} · ${date(source.published)} · ${source.locator}`;
  node.setAttribute("aria-label", `Fuente ${index + 1}: ${node.title}`);
  return node;
}

function claimNode(claim: Claim, sources: Source[]): HTMLElement {
  const node = el("p", undefined, "claim");
  const labels = { hecho: "Hecho", inferencia: "Inferencia", estimacion: "Estimación", programado: "Programado", limite: "Límite" };
  node.append(el("span", labels[claim.kind], `claim-kind ${claim.kind}`), document.createTextNode(` ${claim.text} `));
  for (const source of claim.sources) node.append(citation(source, sources), document.createTextNode(" "));
  return node;
}

export function formatMetric(value: number | null, percent = false, signed = false): string {
  if (value === null) return "No disponible";
  return new Intl.NumberFormat("es-MX", {
    minimumFractionDigits: percent ? 1 : 0, maximumFractionDigits: percent ? 1 : 0,
    signDisplay: signed ? "exceptZero" : "auto",
  }).format(value) + (percent ? "%" : "");
}

function trafficTable(issue: Issue): HTMLElement {
  const wrapper = el("div", undefined, "traffic-scroll");
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", "Tráfico reportado; tabla desplazable horizontalmente");
  const table = el("table");
  table.append(el("caption", `Tráfico reportado · ${issue.label}`));
  const head = el("thead");
  const row = el("tr");
  for (const title of ["Aerolínea", "Pasajeros (miles)", "Var. pasajeros", "ASM (millones)", "Var. ASM", "Var. RPM", "Ocupación"]) {
    const th = el("th", title);
    th.scope = "col";
    row.append(th);
  }
  head.append(row);
  const body = el("tbody");
  for (const metric of issue.traffic) {
    const tr = el("tr");
    const name = el("th", `${metric.airline} `);
    name.scope = "row";
    name.append(citation(metric.source, issue.sources));
    tr.append(name);
    const fields: [keyof Traffic, boolean, boolean][] = [
      ["passengers_thousands", false, false], ["passengers_yoy_pct", true, true],
      ["asm_millions", false, false], ["asm_yoy_pct", true, true],
      ["rpm_yoy_pct", true, true], ["load_factor_pct", true, false],
    ];
    for (const [key, percent, signed] of fields) tr.append(el("td", formatMetric(metric[key] as number | null, percent, signed)));
    body.append(tr);
  }
  table.append(head, body);
  wrapper.append(table);
  return wrapper;
}

function masthead(): HTMLElement {
  const head = el("div", undefined, "publication-title");
  head.append(el("p", "AVIACIÓN MEXICANA", "eyebrow"), el("h1", "Airline Monthly"));
  return head;
}

export function renderArchive(root: HTMLElement, issues: Issue[]): void {
  root.replaceChildren(masthead(), el("h2", "Archivo mensual"));
  const list = el("div", undefined, "archive-list");
  for (const issue of [...issues].sort((a, b) => b.id.localeCompare(a.id))) {
    const article = el("article");
    article.append(el("p", issue.label, "eyebrow"), el("span", "Piloto · Borrador", "draft"));
    const title = el("h3");
    title.append(link(issue.title, issueRoute(issue.id)));
    article.append(title);
    list.append(article);
  }
  root.append(list);
  document.title = "Archivo mensual · Airline Monthly";
}

export function renderIssue(root: HTMLElement, issue: Issue): void {
  const cover = el("header", undefined, "issue-cover");
  cover.append(masthead());
  const meta = el("div", undefined, "issue-meta");
  meta.append(el("p", issue.label), el("span", "Piloto · Borrador para revisión", "draft"));
  cover.append(meta, el("h2", issue.title), el("p", `Corte de fuentes: ${date(issue.cutoff)} (UTC)`, "cutoff"));
  const layout = el("div", undefined, "issue-layout");
  const contents = el("nav", undefined, "issue-index");
  contents.setAttribute("aria-label", "Índice de la edición");
  contents.append(el("h2", "En esta edición"));
  for (const section of issue.sections) contents.append(link(section.title, issueRoute(issue.id, section.id)));
  contents.append(link("Fuentes y método", issueRoute(issue.id, "fuentes")));
  const copy = el("div", undefined, "issue-copy");
  for (const section of issue.sections) {
    const node = el("section", undefined, `editorial-section ${section.id}`);
    node.id = section.id;
    const heading = el("h2", section.title);
    heading.tabIndex = -1;
    node.append(heading);
    if (section.id === "resultados") node.append(trafficTable(issue));
    for (const story of section.stories) {
      const article = el("article");
      article.append(el("h3", story.title));
      for (const claim of story.claims) article.append(claimNode(claim, issue.sources));
      node.append(article);
    }
    copy.append(node);
  }
  const sources = el("section", undefined, "editorial-section sources");
  sources.id = "fuentes";
  const heading = el("h2", "Fuentes y método");
  heading.tabIndex = -1;
  sources.append(heading);
  const methodology = el("details");
  methodology.append(el("summary", "Cómo leer esta edición"));
  for (const text of issue.methodology) methodology.append(el("p", text));
  sources.append(methodology);
  const list = el("ol");
  for (const source of issue.sources) {
    const item = el("li");
    item.append(link(`${source.publisher} · ${source.title}`, source.url),
      el("p", `Publicado: ${date(source.published)} · Consultado: ${date(source.accessed)} · ${source.locator}`));
    list.append(item);
  }
  sources.append(list);
  copy.append(sources);
  layout.append(contents, copy);
  root.replaceChildren(cover, layout);
  document.title = `${issue.label} · Airline Monthly`;
}

export function renderNotFound(root: HTMLElement): void {
  root.replaceChildren(masthead(), el("h2", "Edición no disponible"), link("Ir al archivo mensual", "#archivo"));
  document.title = "Edición no disponible · Airline Monthly";
}
