import type { ChatChart, ChatConversation, ChatEvent, ChatMessage } from "../../types/chat";
import { buildChatContext, describeChatContext } from "./context";
import { messageFromPayload, safeReferences } from "./markdown";
import { mountPanelControls, resizeDashboardCharts } from "./panel-controls";
import { renderMessages } from "./render";
import { MAX_INPUT, PANEL_HTML } from "./template";
import { ChatApiError, ChatTransport } from "./transport";
import "./chat.css";

const MAX_ANSWER = 20_000;
const STORAGE_KEY = "airline-tracker.chat.conversation-id";
const API_URL = import.meta.env.VITE_CHAT_API_URL ?? "/api/chat";
const TERMINAL = new Set(["completed", "failed", "cancelled"]);

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

function storage(action: (store: Storage) => string | null | void): string | null {
  try { return action(window.localStorage) ?? null; } catch { return null; }
}

export function mountChat(): void {
  // The login session lives only in memory: a reload asks for the password again.
  let session: string | undefined;
  let authMode: "local" | "password" | undefined;
  const transport = new ChatTransport(API_URL, () => session);
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
  panel.innerHTML = PANEL_HTML;
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
  const passwordInput = query<HTMLInputElement>("#chat-password");
  const accessError = query<HTMLElement>("[data-chat-access-error]");
  const logoutButton = query<HTMLButtonElement>("[data-chat-logout]");

  const turns = new Map<string, string>();
  const paintMessages = () => renderMessages(messagesNode, state.messages, {
    canRetry: (message) => Boolean(message.retryMessageId || (message.turn_id && ["failed", "cancelled"].includes(turns.get(message.turn_id) ?? ""))),
    onRetry: (message) => {
      const prior = state.messages.slice(0, state.messages.indexOf(message)).reverse().find((candidate) => candidate.role === "user");
      if (prior) void submitMessage(prior.content);
    },
  });

  const setBusy = (busy: boolean) => {
    state.activeTurn = busy ? state.activeTurn : undefined;
    sendButton.disabled = busy;
    input.disabled = busy;
    cancelButton.hidden = !busy;
    sendButton.textContent = busy ? "En proceso" : "Enviar";
  };

  const setContextLabel = () => {
    query<HTMLElement>("[data-chat-context]").textContent = `Contexto: ${describeChatContext(buildChatContext(state.focusedCard))}`;
  };

  const requireLogin = (message = "Ingresa la contraseña para preguntar.") => {
    session = undefined;
    logoutButton.hidden = true;
    accessForm.hidden = false;
    statusNode.textContent = message;
    passwordInput.focus();
  };

  // Returns true when the error was an expired or missing login.
  const handleAuthError = (error: unknown): boolean => {
    if (error instanceof ChatApiError && error.status === 401 && authMode !== "local") {
      requireLogin("Tu sesión terminó. Ingresa la contraseña de nuevo.");
      return true;
    }
    return false;
  };

  function renderTurnEvent(event: ChatEvent): void {
    const turnId = typeof event.turn_id === "string" ? event.turn_id : state.activeTurn;
    const assistantFor = () => state.messages.find((candidate) => candidate.turn_id === turnId && candidate.role === "assistant");
    if (event.type === "turn.queued" || event.type === "turn.started") {
      statusNode.textContent = event.type === "turn.queued" ? "Pregunta en cola…" : "Analizando datos publicados…";
      if (turnId) turns.set(turnId, "running");
    } else if (event.type === "message.delta") {
      let message = assistantFor();
      if (!message) {
        message = { id: randomId(), role: "assistant", content: "", turn_id: turnId, pending: true };
        state.messages.push(message);
      }
      const text = typeof event.text === "string" ? event.text.slice(0, Math.max(0, MAX_ANSWER - message.content.length)) : "";
      message.content += text;
      paintMessages();
    } else if (event.type === "tool.started") {
      statusNode.textContent = "Consultando una fuente autorizada…";
    } else if (event.type === "tool.completed") {
      statusNode.textContent = "Consulta completada; preparando respuesta…";
    } else if (event.type === "message.completed") {
      let message = assistantFor();
      if (!message) { message = { id: randomId(), role: "assistant", content: "", turn_id: turnId }; state.messages.push(message); }
      Object.assign(message, messageFromPayload(event), { pending: false });
      paintMessages();
    } else if (event.type === "turn.completed" || event.type === "turn.cancelled" || event.type === "turn.failed") {
      const outcome = event.type === "turn.completed" ? "completed" : event.type === "turn.cancelled" ? "cancelled" : "failed";
      if (turnId) {
        turns.set(turnId, outcome);
        const message = assistantFor();
        if (message) message.pending = false;
      }
      statusNode.textContent = event.type === "turn.completed" ? "Respuesta completa." : event.type === "turn.cancelled" ? "Turno cancelado." : "No se pudo completar la respuesta. Puedes reintentar.";
      paintMessages();
      setBusy(false);
    }
  }

  function loadConversation(conversation: ChatConversation): void {
    state.conversationId = conversation.id;
    state.snapshotVersion = conversation.snapshot_version;
    state.messages = conversation.messages.map((message) => ({
      ...message,
      references: safeReferences(message.references ?? (message as ChatMessage & { payload?: { references?: unknown } }).payload?.references),
      chart: (message as ChatMessage & { payload?: { chart?: unknown } }).payload?.chart as ChatChart | undefined ?? message.chart,
    }));
    for (const turn of conversation.turns) turns.set(turn.id, turn.status);
    const active = [...conversation.turns].reverse().find((turn) => turn.status === "pending" || turn.status === "running");
    if (!active) return;
    state.activeTurn = active.id;
    state.lastSequence = 0;
    const partial = state.messages.find((message) => message.role === "assistant" && message.turn_id === active.id);
    if (partial) { partial.content = ""; partial.pending = true; }
    else state.messages.push({ id: randomId(), role: "assistant", content: "", turn_id: active.id, pending: true });
    setBusy(true);
    statusNode.textContent = "Retomando respuesta sin reenviar la pregunta…";
    void listen(active.id);
  }

  async function ensureConversation(): Promise<void> {
    noticeNode.textContent = "";
    statusNode.textContent = "Conectando con el servicio…";
    try {
      const health = await transport.health();
      authMode = health.auth;
      if (authMode === "password" && !session) { requireLogin(); return; }
      let conversation: ChatConversation | undefined;
      const previousId = storage((store) => store.getItem(STORAGE_KEY));
      if (previousId) {
        try { conversation = await transport.conversation(previousId); }
        catch (error) {
          if (!(error instanceof ChatApiError) || error.status !== 404) throw error;
          storage((store) => store.removeItem(STORAGE_KEY));
        }
      }
      if (conversation) loadConversation(conversation);
      else {
        const created = await transport.createConversation();
        state.conversationId = created.id;
        state.snapshotVersion = created.snapshot_version;
        storage((store) => store.setItem(STORAGE_KEY, created.id));
        state.messages = [];
      }
      const versionNode = query<HTMLElement>("[data-chat-version]");
      versionNode.textContent = `Datos: ${state.snapshotVersion?.slice(0, 8) ?? "—"}`;
      versionNode.title = state.snapshotVersion ? `Versión completa: ${state.snapshotVersion}` : "Versión del snapshot no disponible";
      if (health.snapshot_version && state.snapshotVersion && health.snapshot_version !== state.snapshotVersion) {
        noticeNode.textContent = `Los datos cambiaron desde esta conversación (${state.snapshotVersion} → ${health.snapshot_version}). Inicia una conversación nueva para consultar la versión actual.`;
      }
      paintMessages();
      if (!state.activeTurn) statusNode.textContent = "Puedes preguntar sobre las métricas y fuentes disponibles.";
    } catch (error) {
      statusNode.textContent = "";
      if (handleAuthError(error)) return;
      noticeNode.textContent = `No se pudo conectar con Airline Tracker: ${errorText(error)}`;
    }
  }

  // A stream that ends without a terminal event is settled from the stored
  // turn state, so the composer is never left locked.
  async function settleTurn(turnId: string, reason: string): Promise<void> {
    let status: string | undefined;
    try {
      const conversation = state.conversationId ? await transport.conversation(state.conversationId) : undefined;
      status = conversation?.turns.find((turn) => turn.id === turnId)?.status;
      if (conversation && status && TERMINAL.has(status)) { loadConversation(conversation); turns.set(turnId, status); }
    } catch (error) { if (handleAuthError(error)) status = undefined; }
    if (state.activeTurn !== turnId) return;
    const assistant = state.messages.find((message) => message.turn_id === turnId && message.role === "assistant");
    if (assistant) assistant.pending = false;
    if (!status || !TERMINAL.has(status)) {
      turns.set(turnId, "failed");
      statusNode.textContent = `Se perdió la conexión con el flujo: ${reason}. La pregunta no se reenvió; puedes reintentar.`;
    } else statusNode.textContent = status === "completed" ? "Respuesta completa." : "No se pudo completar la respuesta. Puedes reintentar.";
    setBusy(false);
    paintMessages();
  }

  async function listen(turnId: string): Promise<void> {
    const abort = new AbortController();
    state.abort = abort;
    let attempts = 0;
    let lastError = "el servidor cerró la conexión";
    while (!abort.signal.aborted && state.activeTurn === turnId && attempts < 5) {
      try {
        const next = await transport.streamEvents(turnId, state.lastSequence, abort.signal, (event) => {
          attempts = 0; // progress resets the reconnect budget
          if (typeof event.seq === "number") state.lastSequence = Math.max(state.lastSequence, event.seq);
          renderTurnEvent(event);
        });
        state.lastSequence = Math.max(state.lastSequence, next);
      } catch (error) {
        if (abort.signal.aborted) return;
        if (handleAuthError(error)) { setBusy(false); return; }
        lastError = errorText(error);
      }
      if (abort.signal.aborted || state.activeTurn !== turnId) return;
      attempts += 1;
      await new Promise((resolve) => window.setTimeout(resolve, Math.min(250 * attempts, 1200)));
    }
    if (!abort.signal.aborted && state.activeTurn === turnId) await settleTurn(turnId, lastError);
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
      const result = await transport.sendMessage(state.conversationId, content, buildChatContext(state.focusedCard), randomId());
      state.activeTurn = result.turn_id;
      state.lastSequence = 0;
      await listen(result.turn_id);
    } catch (error) {
      setBusy(false);
      if (handleAuthError(error)) { input.value = content; state.messages.pop(); paintMessages(); return; }
      state.messages.push({ id: randomId(), role: "assistant", content: `No se pudo enviar la pregunta: ${errorText(error)}`, pending: false, retryMessageId: userMessage.id });
      statusNode.textContent = "La pregunta no se envió. Puedes intentarlo de nuevo.";
      paintMessages();
    }
  }

  function resetConversation(): void {
    state.abort?.abort();
    setBusy(false);
    state.conversationId = undefined; state.snapshotVersion = undefined; state.messages = []; state.activeTurn = undefined; state.lastSequence = 0;
    storage((store) => store.removeItem(STORAGE_KEY)); turns.clear(); paintMessages();
  }

  accessForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = passwordInput.value;
    passwordInput.value = "";
    accessError.textContent = "";
    if (!password) return;
    try {
      session = (await transport.login(password)).session;
      accessForm.hidden = true;
      logoutButton.hidden = false;
      await ensureConversation();
      input.focus();
    } catch (error) {
      if (error instanceof ChatApiError && error.status === 429) {
        const minutes = Math.max(1, Math.ceil((error.retryAfterSeconds ?? 60) / 60));
        accessError.textContent = `Demasiados intentos. Espera ${minutes} min.`;
      } else accessError.textContent = error instanceof ChatApiError && error.status === 401 ? "Contraseña incorrecta." : `No se pudo entrar: ${errorText(error)}`;
      passwordInput.focus();
    }
  });

  logoutButton.addEventListener("click", async () => {
    try { await transport.logout(); } catch { /* the in-memory session is dropped anyway */ }
    resetConversation();
    requireLogin("Sesión cerrada.");
  });

  async function openChat(card?: Element): Promise<void> {
    if (card) state.focusedCard = card;
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    document.body.classList.add("chat-open");
    setContextLabel();
    resizeDashboardCharts();
    if (!state.conversationId) await ensureConversation();
    if (accessForm.hidden) input.focus();
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
    catch (error) { if (!handleAuthError(error)) statusNode.textContent = `No se pudo cancelar el turno: ${errorText(error)}`; }
  });
  query<HTMLButtonElement>("[data-chat-new]").addEventListener("click", async () => {
    if (state.activeTurn) { try { await transport.cancel(state.activeTurn); } catch { /* new session may still proceed */ } }
    resetConversation();
    await ensureConversation();
    if (accessForm.hidden) input.focus();
  });
  query<HTMLButtonElement>("[data-chat-delete]").addEventListener("click", async () => {
    if (!state.conversationId) { state.messages = []; paintMessages(); return; }
    if (state.activeTurn) { state.abort?.abort(); try { await transport.cancel(state.activeTurn); } catch { /* deletion will settle ownership */ } }
    try {
      await transport.deleteConversation(state.conversationId);
      resetConversation();
      statusNode.textContent = "Conversación eliminada.";
    } catch (error) { if (!handleAuthError(error)) noticeNode.textContent = `No se pudo eliminar la conversación: ${errorText(error)}`; }
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
  // Context follows an explicit click or keyboard focus on a card, never hover:
  // moving the pointer toward the panel must not change the question's context.
  const cardListener = (event: Event) => {
    if (panel.contains(event.target as Node) || launcher.contains(event.target as Node)) return;
    const card = (event.target as Element | null)?.closest?.(".chart-card, .flights-shell, .kpi-card");
    if (card) { state.focusedCard = card; setContextLabel(); }
  };
  document.addEventListener("click", cardListener, true);
  document.addEventListener("focusin", cardListener, true);

  mountPanelControls(panel, resizer, closeChat);
  setContextLabel();
}
