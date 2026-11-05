// One reading sheet for the global quarter. Approved issuer documents remain
// the source of every company paragraph; no Industry approval is synthesized.
import { currentPeriodId } from "../../state/period";
import type { AnalysisDocument } from "../../types/domain";
import { selectedReading } from "./reading-periods";
import { applyCitations, citationsByClaim, emphasized, fetchAnalysis } from "./narrative";
import { loadEditorialReview, type ReadingAnalysis } from "./editorial-review";

const issuers = [
  ["AEROMEXICO", "Aeroméxico"], ["VIVA_AEROBUS", "Viva"], ["VOLARIS", "Volaris"],
] as const;
let epoch = 0;

// Emphasize the business result and its counterpoint, rather than every number.
// Matches only decorate existing text; they never supply a missing assertion.
function emphasisPhrases(text: string): string[] {
  return [
    ...text.matchAll(/(?:facturó US\$[\d,.]+ millones|ingresos trimestrales (?:a|de) [\d,.]+ millones de dólares|resultado neto de -?[\d,.]+ millones de dólares|margen operativo terminó en [\d,.]+%|US\$-?[\d,.]+ millones|[\d,.]+ dólares por pasajero con boleto|[\d,.]+ aviones en tierra|margen operativo de [\d,.]+%|TRASM, alcanzó [\d,.]+ centavos de dólar)/gi),
  ].map(match => match[0]).concat([
    "el costo equivalente aumentó más deprisa", "una operación restringida por motores",
    "menos pasajeros", "puntos de lealtad", "por problemas de motores Pratt & Whitney",
    "Los complementarios fueron mayores que la tarifa base", "pérdida neta",
  ].filter(phrase => text.includes(phrase)));
}

function renderComplete(documents: Array<ReadingAnalysis | null>): void {
  const card = document.getElementById("reading-full-card");
  const host = document.getElementById("reading-full-copy");
  if (!card || !host) return;
  host.replaceChildren();
  card.hidden = !documents.some(Boolean);
  for (const [index, analysis] of documents.entries()) {
    if (!analysis) continue;
    const article = document.createElement("article");
    article.dataset.entity = index === 0 ? "INDUSTRY" : issuers[index - 1]![0];
    const heading = document.createElement("h3");
    heading.textContent = `${index === 0 ? "Industria" : issuers[index - 1]![1]}: ${analysis.thesis}`;
    article.append(heading);
    const citations = citationsByClaim(analysis);
    for (const section of analysis.sections) {
      const part = document.createElement("section");
      const subheading = document.createElement("h4");
      subheading.textContent = section.title;
      part.append(subheading);
      section.paragraphs.forEach((text, paragraphIndex) => {
        const paragraph = document.createElement("p");
        const opening = text.split(/(?<=\.)\s/)[0] ?? "";
        const lead = opening.length <= 150 ? opening : "";
        paragraph.innerHTML = emphasized(text, lead, emphasisPhrases(text));
        applyCitations(paragraph, citations.get(section.claim_ids[paragraphIndex] ?? "") ?? []);
        part.append(paragraph);
      });
      article.append(part);
    }
    host.append(article);
  }
}

function itemsFor(analysis: ReadingAnalysis): AnalysisDocument["summary_items"] {
  // Keep one paragraph per issuer. AM's sales and cost claims express the
  // central contrast; peers already have a single approved entry in Q3.
  const priorities = ["sales", "fuel", "summary_business", "summary_unit"];
  if (analysis.entity_key === undefined || analysis.entity_key === "AEROMEXICO") {
    const chosen = priorities.flatMap(id => analysis.summary_items.filter(item => item.claim_id === id));
    if (chosen.length) return chosen.slice(0, 2);
  }
  return analysis.summary_items.slice(0, 1);
}

export async function renderIndustryReading(): Promise<void> {
  const turn = ++epoch;
  const period = currentPeriodId();
  const copy = document.getElementById("narrative-copy");
  const title = document.getElementById("executive-reading-title");
  if (!copy || !title || !period) return;
  title.textContent = "Industria";
  copy.dataset.period = period;
  copy.dataset.entity = "INDUSTRY";
  copy.textContent = "Cargando lectura…";
  const fullCard = document.getElementById("reading-full-card");
  if (fullCard) fullCard.hidden = true;
  document.getElementById("reading-full-copy")?.replaceChildren();
  const full = document.getElementById("reading-full") as HTMLDetailsElement | null;
  if (full) full.open = false;
  const keys = ["INDUSTRY", ...issuers.map(([key]) => key)];
  let review;
  try { review = await loadEditorialReview(period); }
  catch (error) { if (turn === epoch) copy.textContent = String(error); return; }
  if (turn !== epoch || currentPeriodId() !== period) return;
  const documents = review ? keys.map(key => review.analyses[key]!) : await Promise.all(keys.map(key => selectedReading(key)
    ? fetchAnalysis(key, period) : Promise.resolve(null)));
  if (turn !== epoch || currentPeriodId() !== period) return;
  const [industry, ...companies] = documents;
  const list = document.createElement("ul");
  list.className = "analysis-summary";
  const append = (label: string, text: string, phrases: string[] = []) => {
    const li = document.createElement("li");
    const lead = document.createElement("strong");
    lead.textContent = `${label}. `;
    const body = document.createElement("span");
    body.innerHTML = emphasized(text, "", [...phrases, ...emphasisPhrases(text)]);
    li.append(lead, body);
    list.append(li);
    return li;
  };
  if (industry) {
    title.textContent = industry.thesis.replace(/^Industria:\s*/i, "");
    const item = industry.summary_items.find(item => item.claim_id === "s_revenue") ?? industry.summary_items[0];
    if (item) {
      const li = append("Industria", item.text, [item.lead ?? "", ...(item.emphasis ?? [])]);
      applyCitations(li, citationsByClaim(industry).get(item.claim_id) ?? []);
    }
  } else if (period === "2026Q3" && companies.every(Boolean)) {
    // Local editorial synthesis of the three published issuer entries, not
    // a newly approved Industry thesis or a financial aggregate.
    title.textContent = "Mayores ingresos, rentabilidad bajo presión";
    const li = append("Industria", "Las tres aerolíneas aumentaron sus ingresos frente al mismo trimestre del año anterior. El crecimiento de ventas convivió con presión sobre la rentabilidad: Aeroméxico redujo su margen operativo, mientras Viva y Volaris reportaron pérdidas netas.", ["aumentaron sus ingresos", "presión sobre la rentabilidad"]);
    const sources = companies.flatMap((analysis, index) => {
      if (!analysis) return [];
      const item = analysis.summary_items.find(item => item.claim_id === (index === 0 ? "fuel" : "entry"));
      const citations = item && citationsByClaim(analysis).get(item.claim_id);
      const citation = citations && (index === 0 ? citations.find(source => source.value === "11.7%") : citations[0]);
      return citation ? [{ ...citation, value: "frente al mismo trimestre del año anterior.", label: String(index + 1) }] : [];
    });
    applyCitations(li, sources);
  } else {
    append("Industria", "Sin lectura publicada para el trimestre seleccionado.");
  }
  issuers.forEach(([, label], index) => {
    const analysis = companies[index];
    if (!analysis) {
      append(label, "Sin lectura publicada para el trimestre seleccionado.");
      return;
    }
    const items = itemsFor(analysis);
    const text = items.map(item => {
      if (review || index !== 0 || period !== "2026Q3") return item.text;
      if (item.claim_id === "sales") return item.text.replace(item.lead ?? "", "").trim().split(" La empresa atribuye")[0];
      return item.text.replace(item.lead ?? "", "").trim().replace(" La mayor venta convivió con una menor rentabilidad.", "");
    }).join(" ");
    const li = append(label, text, items.flatMap(item => [item.lead ?? "", ...(item.emphasis ?? [])]));
    const citations = citationsByClaim(analysis);
    for (const item of items) applyCitations(li, citations.get(item.claim_id) ?? []);
  });
  copy.replaceChildren(list);
  renderComplete(documents);
}
