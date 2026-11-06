import type { ChatContext } from "../../types/chat";
import { chatCardLabel } from "./card-actions";
import { buildChatContext, describeChatContext } from "./context";

export function attachChatCard(panel: HTMLElement, card?: Element): ChatContext | undefined {
  const attachment = panel.querySelector<HTMLElement>("[data-chat-attachment]")!;
  attachment.hidden = !card;
  if (!card) return undefined;
  const context = structuredClone(buildChatContext(card));
  const title = chatCardLabel(card);
  const period = context.period.replace(/^(\d{2})(\d{2})Q([1-4])$/, "$3T$2");
  const entity = describeChatContext(context).split(" · ")[2];
  panel.querySelector<HTMLElement>("[data-chat-attachment-label]")!.textContent = context.filters?.map_scope
    ? describeChatContext(context) : card.classList.contains("narrative-card")
    ? `${title} · ${period}` : `${title} · ${entity} · ${period}`;
  attachment.title = describeChatContext(context);
  return context;
}
