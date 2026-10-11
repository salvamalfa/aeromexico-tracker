import { describe, expect, it } from "vitest";
import { renderExpectedSummary } from "./expected";

describe("expected-result summary", () => {
  it("shows configured labels and scales a stored fraction for a person", () => {
    const host = document.createElement("div");
    renderExpectedSummary(host, {
      status: "answered",
      rows: [{ metric_id: "load_factor", entity_id: "AEROMEXICO", period: "2026Q2", value: 0.849 }],
    });
    expect(host.textContent).toContain("Factor de ocupación");
    expect(host.textContent).toContain("Aeroméxico");
    expect(host.textContent).toContain("2026Q2");
    expect(host.textContent).toContain("84.9 %");
  });

  it("accepts display-label fields without exposing internal identifiers", () => {
    const host = document.createElement("div");
    renderExpectedSummary(host, {
      status: "supported",
      rows: [{ metric_label: "Factor de ocupación", entity_label: "Aeroméxico", period: "2026Q2", value: 0.849 }],
    });
    expect(host.textContent).toContain("Factor de ocupación · Aeroméxico");
    expect(host.textContent).toContain("84.9 %");
  });

  it("keeps missing values as N/D and explains clarify/refuse expectations", () => {
    const host = document.createElement("div");
    renderExpectedSummary(host, {
      status: "needs_clarification",
      rows: [{ metric: "company_passengers", entity: "VOLARIS", period: "2025Q4", value: null }],
    });
    expect(host.textContent).toContain("Debe pedir una aclaración");
    expect(host.textContent).toContain("No disponible (N/D)");
    expect(host.textContent).not.toContain(": 0 pasajeros");
    renderExpectedSummary(host, { status: "unsupported", rows: [] });
    expect(host.textContent).toContain("fuera del alcance o rechazarla");
    renderExpectedSummary(host, { status: "refused", rows: [] });
    expect(host.textContent).toContain("solicitudes sensibles");
  });

  it("summarizes multi-turn criteria for Q01, Q07, and Q11 without claiming missing published rows", () => {
    const criteria = [
      ["fails language switch or changes facts", "Responde en el idioma solicitado sin cambiar los hechos."],
      ["changes the numeric answer", "Mantiene la cifra al simplificar la explicación."],
      ["drops 2T26 or metric context", "Conserva el periodo 2T26 y la misma métrica al cambiar de aerolínea."],
    ];
    for (const [raw, label] of criteria) {
      const host = document.createElement("div");
      renderExpectedSummary(host, {
        status: "multi_turn",
        critical_failures: [raw],
        rubric: { correctness: "pending owner review", usefulness: "pending owner review", writing: "pending owner review" },
      });
      expect(host.textContent).toContain("Evalúa la conversación completa");
      expect(host.textContent).toContain(label);
      expect(host.textContent).toContain("no una referencia numérica");
      expect(host.textContent).not.toContain("no contiene filas publicadas");
      expect(host.textContent).not.toContain("84.9");
      expect(host.textContent).not.toContain("pendiente de revisión humana");
    }
  });

  it("never creates markup from golden values or exposes unknown metric identifiers in the summary", () => {
    const host = document.createElement("div");
    const hostile = '<svg onload="window.__reviewXss=true">';
    renderExpectedSummary(host, {
      status: "answered",
      rows: [{ metric_id: "private-internal-id", entity: hostile, period: "2026Q2", value: 1 }],
    });
    expect(host.textContent).toContain("Entidad sin etiqueta del catálogo");
    expect(host.textContent).not.toContain("private-internal-id");
    expect(host.querySelector("svg")).toBeNull();
  });
});
