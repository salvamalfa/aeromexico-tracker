import september from "../../../config/monthly/issues/2026-09.json";
import type { Issue } from "./model";
import { resolveRoute } from "./model";
import { renderArchive, renderIssue, renderNotFound } from "./render";

// Validated against contracts/editorial/airline-monthly.schema.json before
// producing a preview; this candidate never enters the approved data manifest.
const issues: Issue[] = [september as Issue];
const root = document.getElementById("monthly-content");
if (!root) throw new Error("Falta el contenedor editorial");

function render(focus: boolean): void {
  const route = resolveRoute(location.hash, issues);
  if (route.archive) renderArchive(root!, issues);
  else if (route.issue) renderIssue(root!, route.issue);
  else renderNotFound(root!);
  if (focus || route.section) requestAnimationFrame(() => {
    const target = route.section ? root!.querySelector<HTMLElement>(`#${route.section} h2`) : root;
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ block: "start" });
  });
}

window.addEventListener("hashchange", () => render(true));
document.querySelector<HTMLAnchorElement>(".skip-link")?.addEventListener("click", (event) => {
  event.preventDefault();
  root.focus();
  root.scrollIntoView({ block: "start" });
});
render(false);
