// Share concurrent catalog reads without retaining stale catalogs after a refresh.
const pending = new Map<string, Promise<unknown>>();

export async function fetchPublicationManifest(url: URL): Promise<unknown> {
  let request = pending.get(url.href);
  if (!request) {
    request = fetch(url).then(response => {
      if (!response.ok) throw new Error("No se pudo verificar el catálogo de publicación.");
      return response.json() as Promise<unknown>;
    });
    pending.set(url.href, request);
  }
  try { return await request; }
  finally { if (pending.get(url.href) === request) pending.delete(url.href); }
}
