import { describe, expect, it } from "vitest";
import september from "../../../config/monthly/issues/2026-09.json";
import type { Issue } from "./model";
import { issueRoute, resolveRoute } from "./model";
import { formatMetric, renderArchive, renderIssue } from "./render";

const issue = september as Issue;

describe("Airline Monthly", () => {
  it("preserves missing values and a reported zero distinctly", () => {
    expect(formatMetric(null, true)).toBe("No disponible");
    expect(formatMetric(0, true)).toBe("0.0%");
    expect(formatMetric(-11, true, true)).toBe("-11.0%");
    expect(formatMetric(1.9, true, true)).toBe("+1.9%");
  });
  it("supports the archive, edition and direct section links", () => {
    expect(resolveRoute("#archivo", [issue])).toEqual({ archive: true });
    expect(resolveRoute(issueRoute(issue.id), [issue]).issue).toBe(issue);
    expect(resolveRoute(issueRoute(issue.id, "analisis"), [issue]).section).toBe("analisis");
    expect(resolveRoute("", [issue]).issue).toBe(issue);
    expect(resolveRoute("#edicion/2026-08", [issue]).issue).toBeUndefined();
    expect(resolveRoute("#edicion/2026-09/desconocida", [issue])).toEqual({});
    expect(resolveRoute('#edicion/2026-09/" onclick="x', [issue])).toEqual({});
  });
  it("renders only available months, newest first", () => {
    const root = document.createElement("main");
    renderArchive(root, [issue, { ...issue, id: "2026-10", label: "Octubre 2026" }]);
    const links = [...root.querySelectorAll("h3 a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["#edicion/2026-10", "#edicion/2026-09"]);
    expect(root.querySelectorAll("article")).toHaveLength(2);
  });
  it("keeps editorial text inert and does not turn a missing metric into zero", () => {
    const candidate = structuredClone(issue);
    candidate.sections[0]!.stories[0]!.claims[0]!.text = '<img src=x onerror="alert(1)">';
    candidate.traffic[0]!.passengers_thousands = null;
    const root = document.createElement("main");
    renderIssue(root, candidate);
    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toContain('<img src=x onerror="alert(1)">');
    expect(root.querySelector("tbody tr td")?.textContent).toBe("No disponible");
    expect(root.querySelector("caption")?.textContent).toContain("Septiembre 2026");
    expect(root.querySelectorAll("tbody tr")).toHaveLength(3);
  });
  it("fails explicitly on a dangling citation", () => {
    const candidate = structuredClone(issue);
    candidate.traffic[0]!.source = "does-not-exist";
    expect(() => renderIssue(document.createElement("main"), candidate)).toThrow("Fuente ausente");
  });
});
