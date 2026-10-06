export function announceReviewStatus(
  status: HTMLElement,
  caching: boolean,
  cacheFailure: boolean,
  cacheReadFailure: boolean,
  message: string,
  error = false,
): void {
  if (!error && cacheReadFailure && message.startsWith("Se exportaron")) {
    status.textContent = `${message} No se recuperaron todos los cortes guardados; este archivo puede omitir esas calificaciones. El caché no se modificó.`;
    status.setAttribute("data-error", "true");
    return;
  }
  if (!error && caching && cacheFailure) {
    if (message.startsWith("Se exportaron")) {
      status.textContent = `${message} El guardado local sigue indisponible; conserva este archivo antes de salir.`;
      status.setAttribute("data-error", "true");
    }
    return;
  }
  status.textContent = message;
  status.setAttribute("data-error", String(error));
}
