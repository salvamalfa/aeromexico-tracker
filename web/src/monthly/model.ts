export interface Source {
  id: string;
  title: string;
  publisher: string;
  url: string;
  published: string;
  accessed: string;
  locator: string;
  sha256: string;
}

export interface Claim {
  kind: "hecho" | "inferencia" | "estimacion" | "programado" | "limite";
  text: string;
  sources: string[];
}

export interface Story {
  title: string;
  claims: Claim[];
}

export interface Section {
  id: string;
  title: string;
  stories: Story[];
}

export interface Traffic {
  airline: string;
  passengers_thousands: number | null;
  passengers_yoy_pct: number | null;
  asm_millions: number | null;
  asm_yoy_pct: number | null;
  rpm_yoy_pct: number | null;
  load_factor_pct: number | null;
  source: string;
}

export interface Issue {
  id: string;
  label: string;
  title: string;
  status: "borrador";
  cutoff: string;
  sources: Source[];
  traffic: Traffic[];
  sections: Section[];
  methodology: string[];
}

export function issueRoute(id: string, section?: string): string {
  return `#edicion/${id}${section ? `/${section}` : ""}`;
}

export function resolveRoute(hash: string, issues: Issue[]): { issue?: Issue; section?: string; archive?: boolean } {
  if (hash === "#archivo") return { archive: true };
  if (!hash || hash === "#") return { issue: issues[0] };
  const match = /^#edicion\/(\d{4}-\d{2})(?:\/([a-z-]+))?$/.exec(hash);
  if (!match) return {};
  const issue = issues.find((candidate) => candidate.id === match[1]);
  const section = match[2];
  if (section && !issue?.sections.some((candidate) => candidate.id === section) && section !== "fuentes") return {};
  return { issue, section };
}
