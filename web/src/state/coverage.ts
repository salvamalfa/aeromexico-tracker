export const periodLabel = (id: string): string => id.includes("Q") ? `${id.slice(-1)}T${id.slice(2,4)}` : `${id.slice(5)}/${id.slice(0,4)}`;
export function expectedMonths(period: string): string[] {
  if (period.includes("M")) return [period];
  const start = (Number(period.slice(-1)) - 1) * 3 + 1;
  return [0,1,2].map(offset => `${period.slice(0,4)}M${String(start+offset).padStart(2,"0")}`);
}
export function coverageText(period: string, months: string[]): string {
  const expected = expectedMonths(period);
  const covered = [...new Set(months)].filter(id => expected.includes(id)).sort();
  const names = covered.map(id => new Intl.DateTimeFormat("es-MX", {month:"long", timeZone:"UTC"})
    .format(new Date(`${id.slice(0,4)}-${id.slice(5)}-01`)));
  return `${periodLabel(period)} · ${covered.length === expected.length ? "ventana mensual completa" : covered.length ? "parcial" : "sin datos"}: ${covered.length} de ${expected.length} meses${names.length ? ` (${names.join(", ")})` : ""}`;
}
