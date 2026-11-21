// Only boolean settings for modules already present in this dashboard are applied.
const settingsUrl = "https://raw.githubusercontent.com/salvamalfa/aeromexico-tracker/dashboard-settings/modules.json";

export function applyModuleSettings(settings: Record<string, unknown>): void {
  for (const section of document.querySelectorAll<HTMLElement>("[data-dashboard-module]")) {
    const value = settings[section.dataset.dashboardModule!];
    if (typeof value === "boolean") section.hidden = !value;
  }
}

export async function loadModuleSettings(): Promise<void> {
  if (location.hostname !== "salvamalfa.github.io") return;
  try {
    const response = await fetch(settingsUrl, {
      credentials: "omit", referrerPolicy: "no-referrer", signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return;
    const settings = await response.json();
    if (settings && typeof settings === "object" && !Array.isArray(settings)) applyModuleSettings(settings);
  } catch {
    // The public dashboard remains usable with its HTML defaults when offline.
  }
}
