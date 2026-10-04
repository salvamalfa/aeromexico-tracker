import type { ChatChart, ChatConversation, ChatContext, ChatEvent, ChatMessage } from "../../types/chat";
import { renderSafeChart } from "./chart";
import { buildChatContext, describeChatContext } from "./context";
import { messageFromPayload, renderSafeMarkdown, safeReferences } from "./markdown";
import { mountPanelControls, resizeDashboardCharts } from "./panel-controls";
import { ChatApiError, ChatTransport } from "./transport";
import "./chat.css";

const MAX_INPUT = 4000;
const MAX_ANSWER = 20_000;
const STORAGE_KEY = "airline-tracker.chat.conversation-id";
const API_URL = import.meta.env.VITE_CHAT_API_URL ?? "/api/chat";

interface ChatUiState {
  conversationId?: string;
  snapshotVersion?: string;
  messages: ChatMessage[];
  activeTurn?: string;
  abort?: AbortController;
  lastSequence: number;
  focusedCard?: Element;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

function randomId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function mountChat(): void {
  let bearerToken: string | undefined;
  const transport = new ChatTransport(API_URL, () => bearerToken);
  const state: ChatUiState = { messages: [], lastSequence: 0 };
  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "chat-launcher";
  launcher.textContent = "Abrir chat";
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", "airline-chat-panel");
  launcher.setAttribute("aria-label", "Abrir Airline Tracker chat analítico");

  const panel = document.createElement("aside");
  panel.id = "airline-chat-panel";
  panel.className = "chat-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "Airline Tracker chat analítico");
  panel.innerHTML = `
    <div class="chat-resizer" role="separator" tabindex="0" aria-label="Ajustar ancho del panel de chat" aria-orientation="vertical" aria-valuemin="340" aria-valuemax="620"></div>
    <header class="chat-header">
      <div><p class="chat-kicker">Airline Tracker</p><h2>Chat analítico</h2><p class="chat-context" data-chat-context>Contexto: vista actual</p></div>
      <button type="button" class="chat-icon-button" data-chat-close aria-label="Cerrar chat">×</button>
    </header>
    <div class="chat-toolbar">
      <span class="chat-version" data-chat-version title="Versión completa del snapshot">Datos: —</span>
      <div><button type="button" data-chat-new>Nueva conversación</button><button type="button" data-chat-delete>Eliminar</button></div>
    </div>
    <p class="chat-notice" data-chat-notice role="status" aria-live="polite"></p>
    <form class="chat-access" data-chat-access hidden>
      <label for="chat-access-token">Token de acceso (solo esta sesión)</label>
      <input id="chat-access-token" type="password" autocomplete="off" spellcheck="false">
      <button type="submit">Conectar</button>
    </form>
    <ol class="chat-messages" data-chat-messages aria-label="Mensajes de la conversación" aria-live="polite"></ol>
    <div class="chat-status" data-chat-status role="status" aria-live="polite"></div>
    <form class="chat-composer" data-chat-form>
      <label for="chat-input">Pregunta sobre los datos publicados</label>
      <textarea id="chat-input" maxlength="4000" rows="3" placeholder="Ej. Compara el factor de ocupación de este trimestre" required></textarea>
      <div class="chat-composer-foot"><span data-chat-count>0 / 4000</span><button type="submit" data-chat-send>Enviar</button><button type="button" data-chat-cancel hidden>Cancelar turno</button></div>
    </form>`;
  document.body.append(launcher, panel);

  const query = <T extends HTMLElement>(selector: string) => panel.querySelector<T>(selector)!;
  const messagesNode = query<HTMLOListElement>("[data-chat-messages]");
  const statusNode = query<HTMLElement>("[data-chat-status]");
  const noticeNode = query<HTMLElement>("[data-chat-notice]");
  const input = query<HTMLTextAreaElement>("#chat-input");
  const form = query<HTMLFormElement>("[data-chat-form]");
  const sendButton = query<HTMLButtonElement>("[data-chat-send]");
  const cancelButton = query<HTMLButtonElement>("[data-chat-cancel]");
  const closeButton = query<HTMLButtonElement>("[data-chat-close]");
  const resizer = query<HTMLElement>(".chat-resizer");
  const accessForm = query<HTMLFormElement>("[data-chat-access]");

  const paintMessages = () => {
    messagesNode.replaceChildren();
    for (const message of state.messages) {
      const item = document.createElement("li");
      item.className = `chat-message chat-message-${message.role}${message.pending ? " is-pending" : ""}`;
      item.dataset.messageId = message.id;
      const label = document.createElement("span");
      label.className = "chat-message-label";
      label.textContent = message.role === "user" ? "Tú" : "Airline Tracker";
      item.append(label);
      const body = document.createElement("div");
      body.className = "chat-message-body";
      const trustedReferenceUrls = safeReferences(message.references).flatMap((reference) => reference.url ? [reference.url] : []);
      renderSafeMarkdown(body, message.content, trustedReferenceUrls);
      item.append(body);
      if (message.chart) {
        const chartHost = document.createElement("div");
        chartHost.className = "chat-answer-chart";
        chartHost.setAttribute("role", "img");
        chartHost.setAttribute("aria-label", message.chart.title ?? "Gráfica de respuesta");
        item.append(chartHost);
        if (!renderSafeChart(chartHost, message.chart)) chartHost.remove();
      }
      if (message.references?.length) {
        const refs = document.createElement("ul");
        refs.className = "chat-references";
        refs.setAttribute("aria-label", "Fuentes");
        for (const reference of safeReferences(message.references)) {
          const li = document.createElement("li");
          if (reference.url) {
            const anchor = document.createElement("a"); anchor.href = reference.url; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
            anchor.textContent = reference.label; li.append(anchor);
          } else {
            const title = document.createElement("span"); title.textContent = reference.label; li.append(title);
          }
          if (reference.detail) { const detail = document.createElement("small"); detail.textContent = reference.detail; li.append(detail); }
          refs.append(li);
        }
        item.append(refs);
      }
      if (message.role === "assistant" && !message.pending && (message.retryMessageId || (message.turn_id && ["failed", "cancelled"].includes(statusForTurn(message.turn_id) ?? "")))) {
        const retry = document.createElement("button"); retry.type = "button"; retry.className = "chat-retry"; retry.textContent = "Reintentar";
        retry.addEventListener("click", () => {
          const prior = [...state.messages].slice(0, state.messages.indexOf(message)).reverse().find((candidate) => candidate.role === "user");
          if (prior) void submitMessage(prior.content);
        });
        item.append(retry);
      }
      messagesNode.append(item);
    }
    messagesNode.scrollTop = messagesNode.scrollHeight;
  };
  const turns = new Map<string, string>();
  function statusForTurn(turnId: string): string | undefined { return turns.get(turnId); }

  const setBusy = (busy: boolean) => {
    state.activeTurn = busy ? state.activeTurn : undefined;
    sendButton.disabled = busy;
    input.disabled = busy;
    cancelButton.hidden = !busy;
    sendButton.textContent = busy ? "En proceso" : "Enviar";
  };

  const setContextLabel = () => {
    const context = buildChatContext(state.focusedCard);
    const entity = Array.isArray(context.entity) ? context.entity.join(", ") : context.entity;
    query<HTMLElement>("[data-chat-context]").textContent = `Contexto: ${describeChatContext(context)}`;
  };

  function renderTurnEvent(event: ChatEvent): void {
    const turnId = typeof event.turn_id === "string" ? event.turn_id : state.activeTurn;
    if (event.type === "turn.queued" || event.type === "turn.started") {
      statusNode.textContent = event.type === "turn.queued" ? "Pregunta en cola…" : "Analizando datos publicados…";
      if (turnId) turns.set(turnId, "running");
    } else if (event.type === "message.delta") {
      const text = typeof event.text === "string" ? event.text.slice(0, Math.max(0, MAX_ANSWER - (state.messages.find((candidate) => candidate.turn_id === turnId && candidate.role === "assistant")?.content.length ?? 0))) : "";
      let message = state.messages.find((candidate) => candidate.turn_id === turnId && candidate.role === "assistant");
      if (!message) {
        message = { id: randomId(), role: "assistant", content: "", turn_id: turnId, pending: true };
        state.messages.push(message);
      }
      message.content += text;
      paintMessages();
    } else if (event.type === "tool.started") {
      statusNode.textContent = "Consultando una fuente autorizada…";
    } else if (event.type === "tool.completed") {
      statusNode.textContent = "Consulta completada; preparando respuesta…";
    } else if (event.type === "message.completed") {
      const partial = messageFromPayload(event);
      let message = state.messages.find((candidate) => candidate.turn_id === turnId && candidate.role === "assistant");
      if (!message) { message = { id: randomId(), role: "assistant", content: "", turn_id: turnId }; state.messages.push(message); }
      Object.assign(message, partial, { pending: false });
      paintMessages();
    } else if (event.type === "turn.completed" || event.type === "turn.cancelled" || event.type === "turn.failed") {
      const outcome = event.type === "turn.completed" ? "completed" : event.type === "turn.cancelled" ? "cancelled" : "failed";
      if (turnId) {
        turns.set(turnId, outcome);
        const message = state.messages.find((candidate) => candidate.turn_id === turnId && candidate.role === "assistant");
        if (message) message.pending = false;
      }
      statusNode.textContent = event.type === "turn.completed" ? "Respuesta completa." : event.type === "turn.cancelled" ? "Turno cancelado." : "No se pudo completar la respuesta. Puedes reintentar.";
      paintMessages();
      setBusy(false);
    }
  }

  async function ensureConversation(): Promise<void> {
    noticeNode.textContent = "";
    statusNode.textContent = "Conectando con el servicio…";
    try {
      const health = await transport.health() as { status?: string; snapshot_version?: string };
      const currentVersion = health.snapshot_version;
      let conversation: ChatConversation | undefined;
      const previousId = localStorage.getItem(STORAGE_KEY);
      if (previousId) {
        try { conversation = await transport.conversation(previousId); }
        catch (error) {
          if (!(error instanceof ChatApiError) || error.status !== 404) throw error;
          localStorage.removeItem(STORAGE_KEY);
        }
      }
      if (!conversation) {
        const created = await transport.createConversation();
        state.conversationId = created.id;
        state.snapshotVersion = created.snapshot_version;
        localStorage.setItem(STORAGE_KEY, created.id);
        state.messages = [];
      } else {
        state.conversationId = conversation.id;
        state.snapshotVersion = conversation.snapshot_version;
        state.messages = conversation.messages.map((message) => ({
          ...message,
          references: safeReferences(message.references ?? (message as ChatMessage & { payload?: { references?: unknown } }).payload?.references),
          chart: (message as ChatMessage & { payload?: { chart?: unknown } }).payload?.chart as ChatChart | undefined ?? message.chart,
        }));
        const active = [...conversation.turns].reverse().find((turn) => turn.status === "queued" || turn.status === "running" || turn.status === "in_progress");
        if (active) {
          state.activeTurn = active.id;
          state.lastSequence = 0;
          const partial = state.messages.find((message) => message.role === "assistant" && message.turn_id === active.id);
          if (partial) { partial.content = ""; partial.pending = true; }
          else state.messages.push({ id: randomId(), role: "assistant", content: "", turn_id: active.id, pending: true });
          setBusy(true);
          statusNode.textContent = "Retomando respuesta sin reenviar la pregunta…";
          void listen(active.id);
        }
      }
      const versionNode = query<HTMLElement>("[data-chat-version]");
      versionNode.textContent = `Datos: ${state.snapshotVersion?.slice(0, 8) ?? "—"}`;
      versionNode.title = state.snapshotVersion ? `Versión completa: ${state.snapshotVersion}` : "Versión del snapshot no disponible";
      if (currentVersion && state.snapshotVersion && currentVersion !== state.snapshotVersion) {
        noticeNode.textContent = `Los datos cambiaron desde esta conversación (${state.snapshotVersion} → ${currentVersion}). Inicia una conversación nueva para consultar la versión actual.`;
      }
      paintMessages();
      statusNode.textContent = "Puedes preguntar sobre las métricas y fuentes disponibles.";
    } catch (error) {
      statusNode.textContent = "";
      if (error instanceof ChatApiError && (error.status === 401 || error.status === 403)) accessForm.hidden = false;
      noticeNode.textContent = `No se pudo conectar con Airline Tracker: ${errorText(error)}`;
    }
  }

  async function listen(turnId: string): Promise<void> {
    state.abort = new AbortController();
    let attempts = 0;
    while (!state.abort.signal.aborted && attempts < 5) {
      try {
        const next = await transport.streamEvents(turnId, state.lastSequence, state.abort.signal, (event) => {
          if (typeof event.seq === "number") state.lastSequence = Math.max(state.lastSequence, event.seq);
          renderTurnEvent(event);
        });
        state.lastSequence = Math.max(state.lastSequence, next);
        // Event streams may close between replay windows. Reconnect from the
        // last sequence; duplicate frames are discarded by transport.
        if (!state.abort.signal.aborted && state.activeTurn) {
          attempts += 1;
          await new Promise((resolve) => window.setTimeout(resolve, Math.min(250 * attempts, 1200)));
        }
      } catch (error) {
        if (state.abort.signal.aborted) return;
        attempts += 1;
        if (attempts >= 5) {
          statusNode.textContent = `Se perdió la conexión con el flujo: ${errorText(error)}. Puedes reintentar la pregunta.`;
          const assistant = state.messages.find((message) => message.turn_id === turnId && message.role === "assistant");
          if (assistant) assistant.pending = false;
          turns.set(turnId, "failed");
          setBusy(false);
          paintMessages();
        } else await new Promise((resolve) => window.setTimeout(resolve, Math.min(250 * attempts, 1200)));
      }
    }
  }

  async function submitMessage(raw: string): Promise<void> {
    const content = raw.trim();
    if (!content || content.length > MAX_INPUT || state.activeTurn) return;
    if (!state.conversationId) await ensureConversation();
    if (!state.conversationId) return;
    const userMessage: ChatMessage = { id: randomId(), role: "user", content, created_at: new Date().toISOString() };
    state.messages.push(userMessage);
    paintMessages();
    input.value = "";
    query<HTMLElement>("[data-chat-count]").textContent = `0 / ${MAX_INPUT}`;
    setBusy(true);
    statusNode.textContent = "Enviando pregunta…";
    try {
      const context: ChatContext = buildChatContext(state.focusedCard);
      const result = await transport.sendMessage(state.conversationId, content, context, randomId());
      state.activeTurn = result.turn_id;
      state.lastSequence = 0;
      await listen(result.turn_id);
    } catch (error) {
      if (error instanceof ChatApiError && (error.status === 401 || error.status === 403)) accessForm.hidden = false;
      state.messages.push({ id: randomId(), role: "assistant", content: `No se pudo enviar la pregunta: ${errorText(error)}`, turn_id: state.activeTurn, pending: false, retryMessageId: userMessage.id });
      statusNode.textContent = "La pregunta no se envió. Puedes intentarlo de nuevo.";
      setBusy(false);
      paintMessages();
    }
  }

  accessForm.addEventListener("submit", (event) => {
    event.preventDefault();
    bearerToken = query<HTMLInputElement>("#chat-access-token").value.trim() || undefined;
    query<HTMLInputElement>("#chat-access-token").value = "";
    accessForm.hidden = true;
    void ensureConversation();
  });

  async function openChat(card?: Element): Promise<void> {
    if (card) state.focusedCard = card;
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    document.body.classList.add("chat-open");
    setContextLabel();
    resizeDashboardCharts();
    if (!state.conversationId) await ensureConversation();
    input.focus();
  }
  function closeChat(): void {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    document.body.classList.remove("chat-open");
    resizeDashboardCharts();
    launcher.focus();
  }

  launcher.addEventListener("click", () => void openChat());
  closeButton.addEventListener("click", closeChat);
  form.addEventListener("submit", (event) => { event.preventDefault(); void submitMessage(input.value); });
  input.addEventListener("input", () => {
    query<HTMLElement>("[data-chat-count]").textContent = `${input.value.length} / ${MAX_INPUT}`;
    sendButton.disabled = input.value.trim().length === 0 || input.value.length > MAX_INPUT || Boolean(state.activeTurn);
  });
  cancelButton.addEventListener("click", async () => {
    if (!state.activeTurn) return;
    try { await transport.cancel(state.activeTurn); statusNode.textContent = "Solicitando cancelación…"; }
    catch (error) { statusNode.textContent = `No se pudo cancelar el turno: ${errorText(error)}`; }
  });
  query<HTMLButtonElement>("[data-chat-new]").addEventListener("click", async () => {
    if (state.activeTurn) {
      state.abort?.abort();
      try { await transport.cancel(state.activeTurn); } catch { /* new session may still proceed */ }
    }
    setBusy(false);
    state.conversationId = undefined; state.snapshotVersion = undefined; state.messages = []; state.activeTurn = undefined; state.lastSequence = 0;
    localStorage.removeItem(STORAGE_KEY); turns.clear(); paintMessages(); await ensureConversation(); input.focus();
  });
  query<HTMLButtonElement>("[data-chat-delete]").addEventListener("click", async () => {
    if (!state.conversationId) { state.messages = []; paintMessages(); return; }
    if (state.activeTurn) { state.abort?.abort(); try { await transport.cancel(state.activeTurn); } catch { /* deletion will settle ownership */ } }
    try {
      await transport.deleteConversation(state.conversationId);
      setBusy(false);
      localStorage.removeItem(STORAGE_KEY);
      state.conversationId = undefined; state.snapshotVersion = undefined; state.messages = []; state.activeTurn = undefined;
      paintMessages(); statusNode.textContent = "Conversación eliminada.";
    } catch (error) { noticeNode.textContent = `No se pudo eliminar la conversación: ${errorText(error)}`; }
  });

  const cardButton = (card: HTMLElement, label: string) => {
    if (card.querySelector(":scope > .chat-card-action")) return;
    card.classList.add("chat-card-host");
    const button = document.createElement("button"); button.type = "button"; button.className = "chat-card-action";
    button.textContent = "Preguntar a Airline Tracker"; button.setAttribute("aria-label", `Preguntar sobre ${label}`);
    button.addEventListener("click", () => void openChat(card));
    card.append(button);
  };
  const bindCardActions = () => {
    document.querySelectorAll<HTMLElement>(".chart-card, .kpi-card, .flight-kpi, .narrative-card").forEach((card) => {
      const title = card.querySelector<HTMLElement>(".chart-title")?.textContent?.trim() ?? "esta gráfica";
      cardButton(card, title);
    });
    document.querySelectorAll<HTMLElement>(".flights-shell").forEach((card) => cardButton(card, "la vista de vuelos"));
  };
  bindCardActions();
  const observer = new MutationObserver(bindCardActions);
  observer.observe(document.querySelector(".page-shell") ?? document.body, { childList: true, subtree: true });
  window.addEventListener("reader-tab-visible", bindCardActions);
  const cardListener = (event: Event) => {
    if (panel.contains(event.target as Node) || launcher.contains(event.target as Node)) return;
    const card = (event.target as Element | null)?.closest?.(".chart-card, .flights-shell, .kpi-card");
    if (card) { state.focusedCard = card; setContextLabel(); }
  };
  document.addEventListener("pointerover", cardListener, true);
  document.addEventListener("focusin", cardListener, true);

  mountPanelControls(panel, resizer, closeChat);
  setContextLabel();
}
