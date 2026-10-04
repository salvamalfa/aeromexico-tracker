// Static panel markup. Dynamic text is always assigned with textContent.
export const MAX_INPUT = 4000;

export const PANEL_HTML = `
    <div class="chat-resizer" role="separator" tabindex="0" aria-label="Ajustar ancho del panel de chat" aria-orientation="vertical" aria-valuemin="340" aria-valuemax="620"></div>
    <header class="chat-header">
      <div><p class="chat-kicker">Airline Tracker</p><h2>Chat analítico</h2><p class="chat-context" data-chat-context>Contexto: vista actual</p></div>
      <button type="button" class="chat-icon-button" data-chat-close aria-label="Cerrar chat">×</button>
    </header>
    <div class="chat-toolbar">
      <span class="chat-version" data-chat-version title="Versión completa del snapshot">Datos: —</span>
      <div><button type="button" data-chat-new>Nueva conversación</button><button type="button" data-chat-delete>Eliminar</button><button type="button" data-chat-logout hidden>Salir</button></div>
    </div>
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
      <label for="chat-input">Pregunta sobre los datos publicados</label>
      <textarea id="chat-input" maxlength="${MAX_INPUT}" rows="3" placeholder="Ej. Compara el factor de ocupación de este trimestre" required></textarea>
      <div class="chat-composer-foot"><span data-chat-count>0 / ${MAX_INPUT}</span><button type="submit" data-chat-send>Enviar</button><button type="button" data-chat-cancel hidden>Cancelar turno</button></div>
    </form>`;
