// Static panel markup. Dynamic text is always assigned with textContent.
export const MAX_INPUT = 4000;

export const PANEL_HTML = `
    <div class="chat-resizer" role="separator" tabindex="0" aria-label="Ajustar ancho del panel de chat" aria-orientation="vertical" aria-valuemin="340" aria-valuemax="620"></div>
    <header class="chat-header">
      <h2>Chat</h2>
      <div class="chat-header-actions">
        <button type="button" class="chat-icon-button" data-chat-new aria-label="Nueva conversación" title="Nueva conversación"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4Z"/></svg></button>
        <button type="button" class="chat-icon-button" data-chat-close aria-label="Cerrar chat" title="Cerrar chat"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m18 6-12 12M6 6l12 12"/></svg></button>
        <button type="button" class="chat-icon-button" data-chat-logout hidden>Salir</button>
      </div>
    </header>
    <span data-chat-context hidden></span>
    <span data-chat-version hidden></span>
    <button type="button" data-chat-delete hidden>Eliminar conversación</button>
    <p class="chat-notice" data-chat-notice role="status" aria-live="polite"></p>
    <form class="chat-access" data-chat-access hidden>
      <label for="chat-password">Contraseña</label>
      <input id="chat-password" type="password" autocomplete="current-password" maxlength="256" required>
      <button type="submit">Entrar</button>
      <p class="chat-access-error" data-chat-access-error role="alert"></p>
    </form>
    <ol class="chat-messages" data-chat-messages aria-label="Mensajes de la conversación" aria-live="polite"></ol>
    <div class="chat-status" data-chat-status role="status" aria-live="polite"></div>
    <form class="chat-composer" data-chat-form>
      <div class="chat-attachment" data-chat-attachment hidden role="group" aria-live="polite" aria-label="Contexto adjunto">
        <span aria-hidden="true">▧</span><span data-chat-attachment-label></span>
        <button type="button" data-chat-attachment-remove aria-label="Quitar contexto adjunto">×</button>
      </div>
      <label for="chat-input" class="sr-only">Pregunta sobre los datos publicados</label>
      <textarea id="chat-input" maxlength="${MAX_INPUT}" rows="2" placeholder="Escribe tu pregunta…" aria-describedby="chat-count" required></textarea>
      <div class="chat-composer-foot"><span id="chat-count" class="sr-only" data-chat-count>0 / ${MAX_INPUT}</span><button type="submit" data-chat-send aria-label="Enviar pregunta" title="Enviar pregunta" disabled><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button><button type="button" data-chat-cancel hidden>Cancelar turno</button></div>
    </form>`;

export function createChatPanel(): HTMLElement {
  const panel = document.createElement("aside");
  panel.id = "airline-chat-panel";
  panel.className = "chat-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Ayuda con los datos");
  panel.innerHTML = PANEL_HTML;
  return panel;
}
