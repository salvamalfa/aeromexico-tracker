import type { ChatContext, ChatMessage } from "../../types/chat";
import { errorText, randomId } from "./util";
import { MAX_INPUT } from "./template";
import { ChatSubmissionLedger, isDefiniteSendRejection } from "./submission-ledger";

interface SubmitState {
  conversationId?: string;
  activeTurn?: string;
  lastSequence: number;
  focusedCard?: Element;
  messages: ChatMessage[];
}

interface SubmitOptions {
  state: SubmitState;
  input: HTMLTextAreaElement;
  count: HTMLElement;
  status: HTMLElement;
  ledger: ChatSubmissionLedger;
  send: (conversation: string, content: string, context: ChatContext, clientMessageId: string) => Promise<{ turn_id: string }>;
  context: (card?: Element) => ChatContext;
  ensureConversation: () => Promise<void>;
  listen: (turnId: string) => Promise<void>;
  setBusy: (busy: boolean) => void;
  handleAuthError: (error: unknown) => boolean;
  paint: () => void;
}

export function createSubmitController(options: SubmitOptions) {
  const {
    state, input, count, status, ledger, send, context, ensureConversation, listen,
    setBusy, handleAuthError, paint,
  } = options;

  return async function submitMessage(raw: string, retryMessageId?: string): Promise<void> {
    const retry = retryMessageId ? ledger.get(retryMessageId) : undefined;
    const content = retry?.message.content ?? raw.trim();
    if (!content || content.length > MAX_INPUT || state.activeTurn) return;
    if (ledger.hasUnresolved && !retry) return;
    if (!retry && !state.conversationId) await ensureConversation();
    if (!state.conversationId) return;
    const message = retry?.message ?? {
      id: randomId(), role: "user" as const, content, created_at: new Date().toISOString(),
    };
    const submission = retry ?? {
      message, conversationId: state.conversationId, clientMessageId: randomId(), context: context(state.focusedCard),
    };
    if (!retry) {
      ledger.retain(submission);
      state.messages.push(message);
      paint();
      input.value = "";
      count.textContent = `0 / ${MAX_INPUT}`;
    } else if (submission.conversationId !== state.conversationId) return;
    const wasUnresolved = ledger.isUnresolved(message.id);
    setBusy(true);
    status.textContent = retry && ledger.isUnresolved(message.id)
      ? "Verificando el envío anterior con la misma clave…"
      : "Enviando pregunta…";
    try {
      const result = await send(submission.conversationId, content, submission.context, submission.clientMessageId);
      ledger.markAccepted(message.id, result.turn_id);
      state.activeTurn = result.turn_id;
      state.lastSequence = 0;
      await listen(result.turn_id);
    } catch (error) {
      if (handleAuthError(error)) {
        if (wasUnresolved) {
          ledger.markUnresolved(message.id);
          setBusy(false);
          paint();
          return;
        } else {
          ledger.settle(message.id);
          input.value = content;
          state.messages = state.messages.filter((item) => item.id !== message.id);
        }
        setBusy(false);
        paint();
        return;
      }
      const ambiguous = wasUnresolved || !isDefiniteSendRejection(error);
      if (ambiguous) ledger.markUnresolved(message.id);
      else ledger.settle(message.id);
      setBusy(false);
      const detail = ambiguous
        ? `No se pudo confirmar si el servicio recibió la pregunta: ${errorText(error)}. Reintenta para consultar el mismo envío sin crear otro turno.`
        : `El servicio rechazó la pregunta: ${errorText(error)}. Puedes corregirla e intentarlo de nuevo.`;
      state.messages.push({ id: randomId(), role: "assistant", content: detail, pending: false, retryMessageId: message.id });
      status.textContent = ambiguous
        ? "El resultado del envío es incierto. Usa Reintentar para reutilizar el mismo identificador."
        : "El servicio rechazó la pregunta. Puedes intentarlo de nuevo.";
      paint();
    }
  };
}
