import type { ChatConversation, ChatMessage } from "../../types/chat";
import type { ChatSubmissionLedger } from "./submission-ledger";
import { randomId } from "./util";

interface SettleState {
  conversationId?: string;
  activeTurn?: string;
  messages: ChatMessage[];
}

interface SettleOptions {
  state: SettleState;
  submissions: ChatSubmissionLedger;
  terminal: Set<string>;
  getConversation: (id: string) => Promise<ChatConversation>;
  loadConversation: (conversation: ChatConversation) => void;
  handleAuthError: (error: unknown) => boolean;
  status: HTMLElement;
  setBusy: (busy: boolean) => void;
  paint: () => void;
}

export function createTurnSettler(options: SettleOptions) {
  const { state, submissions, terminal, getConversation, loadConversation, handleAuthError, status, setBusy, paint } = options;
  return async (turnId: string, reason: string): Promise<void> => {
    let outcome: string | undefined;
    try {
      const conversation = state.conversationId ? await getConversation(state.conversationId) : undefined;
      outcome = conversation?.turns.find((turn) => turn.id === turnId)?.status;
      if (conversation && outcome && terminal.has(outcome)) {
        submissions.settleTurn(turnId);
        loadConversation(conversation);
      } else if (conversation && (outcome === "pending" || outcome === "running")) {
        loadConversation(conversation);
        return;
      }
    } catch (error) { if (handleAuthError(error)) outcome = undefined; }
    if (state.activeTurn !== turnId) return;
    const assistant = state.messages.find((message) => message.turn_id === turnId && message.role === "assistant");
    if (assistant) assistant.pending = false;
    if (!outcome || !terminal.has(outcome)) {
      const submission = submissions.forTurn(turnId);
      if (submission) submissions.markUnresolved(submission.message.id);
      if (assistant && submission) assistant.retryMessageId = submission.message.id;
      else if (submission) state.messages.push({
        id: randomId(), role: "assistant",
        content: "No se pudo verificar el turno. Reintenta para recuperar el mismo envío sin crear otro.",
        retryMessageId: submission.message.id,
      });
      status.textContent = `Se perdió la conexión con el flujo: ${reason}. No crees otra pregunta; reintenta para recuperar este turno.`;
    } else status.textContent = outcome === "completed" ? "Respuesta completa." : "No se pudo completar la respuesta. Puedes reintentar.";
    setBusy(false);
    paint();
  };
}
