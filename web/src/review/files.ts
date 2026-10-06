const MAX_FILE_BYTES = 10 * 1024 * 1024;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function readJsonFile(
  file: File,
  hashBytes: (bytes: ArrayBuffer) => Promise<string>,
): Promise<{ value: unknown; contentHash: string }> {
  if (file.size > MAX_FILE_BYTES) throw new Error("El archivo supera el límite de 10 MB.");
  if (!crypto.subtle) throw new Error("Este navegador no permite verificar el archivo. Abre la página por HTTPS o localhost.");
  let bytes: ArrayBuffer;
  try { bytes = await file.arrayBuffer(); } catch { throw new Error("No se pudo leer el archivo."); }
  const contentHash = await hashBytes(bytes);
  try {
    return { value: JSON.parse(new TextDecoder().decode(bytes)) as unknown, contentHash };
  } catch {
    throw new Error("El archivo no contiene JSON válido.");
  }
}

export function downloadJson(value: unknown, filename: string, view: Window): void {
  const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.ownerDocument.body.append(anchor);
  anchor.click();
  anchor.remove();
  view.setTimeout(() => URL.revokeObjectURL(url), 0);
}
