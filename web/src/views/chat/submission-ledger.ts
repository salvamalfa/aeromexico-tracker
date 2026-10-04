import type { ChatContext, ChatMessage } from "../../types/chat";

export interface ChatSubmission {
  message: ChatMessage;
  conversationId: string;
  clientMessageId: string;
  context: ChatContext;
  turnId?: string;
}

const DEFINITE_REJECTIONS = new Set([400, 401, 403, 404, 409, 413, 422, 429]);

export function isDefiniteSendRejection(error: unknown): boolean {
  if (!error || typeof error !== "object" || !("status" in error)) return false;
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" && DEFINITE_REJECTIONS.has(status);
}

/** Keeps one request envelope stable while its POST outcome is unknown. */
export class ChatSubmissionLedger {
  private readonly submissions = new Map<string, ChatSubmission>();
  private unresolvedMessageId?: string;

  get(messageId: string): ChatSubmission | undefined { return this.submissions.get(messageId); }
  get unresolved(): ChatSubmission | undefined {
    return this.unresolvedMessageId ? this.submissions.get(this.unresolvedMessageId) : undefined;
  }
  forTurn(turnId: string): ChatSubmission | undefined {
    return [...this.submissions.values()].find((submission) => submission.turnId === turnId);
  }
  isUnresolved(messageId: string): boolean { return this.unresolvedMessageId === messageId; }
  get hasUnresolved(): boolean { return this.unresolvedMessageId !== undefined; }

  retain(submission: ChatSubmission): void {
    this.submissions.set(submission.message.id, submission);
  }

  markUnresolved(messageId: string): void { this.unresolvedMessageId = messageId; }

  markAccepted(messageId: string, turnId: string): void {
    const submission = this.submissions.get(messageId);
    if (submission) {
      submission.turnId = turnId;
      submission.message.turn_id = turnId;
    }
    if (this.unresolvedMessageId === messageId) this.unresolvedMessageId = undefined;
  }

  settleTurn(turnId: string): void {
    const submission = this.forTurn(turnId);
    if (submission) this.settle(submission.message.id);
  }

  settle(messageId: string): void {
    this.submissions.delete(messageId);
    if (this.unresolvedMessageId === messageId) this.unresolvedMessageId = undefined;
  }

  clear(): void {
    this.submissions.clear();
    this.unresolvedMessageId = undefined;
  }
}
