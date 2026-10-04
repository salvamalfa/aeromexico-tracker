export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

export function randomId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// localStorage can throw (private mode, blocked storage); the panel works without it.
export function storage(action: (store: Storage) => string | null | void): string | null {
  try { return action(window.localStorage) ?? null; } catch { return null; }
}
