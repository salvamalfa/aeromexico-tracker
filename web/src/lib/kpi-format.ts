// Presentation policy for every KPI card: one decimal for measured/scaled
// values and comparisons; whole numbers for discrete counts. Call only when
// rendering, so records, calculations, charts and detailed tables keep precision.
export const KPI_FRACTION_DIGITS = 1;

interface KpiNumberOptions {
  suffix?: string;
  signed?: boolean;
  integer?: boolean;
  missing?: string;
}

export function formatKpiNumber(value: unknown, options: KpiNumberOptions = {}): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return options.missing ?? "No disponible";
  const digits = options.integer ? 0 : KPI_FRACTION_DIGITS;
  const formatted = new Intl.NumberFormat("es-MX", {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
    signDisplay: options.signed ? "always" : "auto",
  }).format(value);
  return formatted + (options.suffix ?? "");
}

// Executive comparisons carry their full-precision value in `raw`. Their
// existing display supplies the unit and sign convention (industry shares do
// not carry a plus sign). Older fixtures without raw can still be displayed.
export function formatKpiComparison(comparison: {
  available: boolean; display: string; raw?: number | null;
}): string {
  if (!comparison.available) return "No disponible";
  const match = /^([+-]?\d+(?:\.\d+)?)(.*)$/.exec(comparison.display);
  if (!match) return "No disponible";
  const suffix = match[2]!;
  const value = comparison.raw === undefined
    ? Number(match[1])
    : comparison.raw == null ? null : comparison.raw * (suffix.startsWith("%") ? 100 : 1);
  return formatKpiNumber(value, { suffix, signed: /^[+-]/.test(match[1]!) });
}
