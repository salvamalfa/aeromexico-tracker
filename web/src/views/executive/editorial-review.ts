import type { AnalysisDocument } from "../../types/domain";

// Drafts deliberately have no approval_event, audit_hash or ledger identity.
export type ReadingAnalysis = Pick<AnalysisDocument,
  "period_id" | "version" | "thesis" | "summary_items" | "sections" | "claims"> & {
  entity_key?: string;
};
export type EditorialReview = {
  schema_version: "editorial_review_v1";
  state: "draft";
  period_id: string;
  analyses: Record<string, ReadingAnalysis>;
};

export async function loadEditorialReview(period: string): Promise<EditorialReview | null> {
  if (!import.meta.env.DEV || new URLSearchParams(location.search).get("review") !== "1") return null;
  if (!/^\d{4}Q[1-4]$/.test(period)) throw new Error("Trimestre de revisión inválido");
  const response = await fetch(`/__editorial-review/${period}.json`, {cache:"no-store"});
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("No se pudo cargar la propuesta editorial");
  const value = await response.json();
  if (value.schema_version !== "editorial_review_v1" || value.state !== "draft" || value.period_id !== period) throw new Error("Propuesta editorial inválida");
  for (const key of ["INDUSTRY", "AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"]) {
    const analysis = value.analyses?.[key];
    if (!analysis || analysis.entity_key !== key || analysis.period_id !== period ||
      typeof analysis.thesis !== "string" || !Array.isArray(analysis.summary_items) ||
      !Array.isArray(analysis.sections) || !Array.isArray(analysis.claims)) throw new Error("Lectura de revisión incompleta");
    const ids = new Set(analysis.claims.map((claim: {claim_id:string}) => claim.claim_id));
    if (analysis.summary_items.some((item: {claim_id:string;text:string}) => !ids.has(item.claim_id) || typeof item.text !== "string") ||
      analysis.sections.some((section: {paragraphs:string[];claim_ids:string[]}) => !Array.isArray(section.paragraphs) || section.paragraphs.length !== section.claim_ids?.length || section.claim_ids.some(id => !ids.has(id)))) throw new Error("Referencias de revisión inválidas");
  }
  return value as EditorialReview;
}
