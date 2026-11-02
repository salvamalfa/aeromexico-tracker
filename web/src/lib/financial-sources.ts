import type { EntityKey } from "../views/shell/carriers";

export interface FinancialSource { label: string; href: string; }

// Exact report URLs already retained in the source catalog and issuer notes.
// Other periods link to the official issuer archive rather than inventing a
// period-specific URL. Industry uses all three issuers for that same period.
export function financialKpiSources(entity: EntityKey, period: string): FinancialSource[] {
  if (entity === "INDUSTRY") return (["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"] as const)
    .flatMap(key => financialKpiSources(key, period));
  if (entity === "AEROMEXICO") return [{label:"Aeroméxico",href:"https://ir.aeromexico.com/financial-information/quarterly-results"}];
  if (entity === "VOLARIS") return [period === "2026Q3"
    ? {label:"Volaris",href:"https://www.sec.gov/Archives/edgar/data/1520504/000129281426005010/ex99-1.htm"}
    : {label:"Volaris",href:"https://ir.volaris.com/news-events/press-releases/"}];
  const vivaReports: Record<string,string> = {
    "2026Q2":"https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-2T26-en.pdf",
    "2026Q3":"https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-3T26-en.pdf",
  };
  return [{label:"Viva",href:vivaReports[period] ?? "https://www.bmv.com.mx/es/emisoras/eventosrelevantes/GVIVA-34292-CGEN_DEUD"}];
}
