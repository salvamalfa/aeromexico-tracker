import type { ChatContext } from "../../types/chat";
import { officialState } from "../flights/official-routes";
import { chatCardLabel, isOfficialMapCard } from "./card-actions";
import { buildChatContext, describeChatContext } from "./context";
import type { ChatHealth } from "./transport";

export function attachChatCard(panel: HTMLElement, card?: Element, useOfficialMap = false): ChatContext | undefined {
  const attachment = panel.querySelector<HTMLElement>("[data-chat-attachment]")!;
  if (!card || (!useOfficialMap && isOfficialMapCard(card))) {
    attachment.hidden = true;
    return undefined;
  }
  attachment.hidden = false;
  const context = structuredClone(buildChatContext(card, useOfficialMap));
  const title = chatCardLabel(card);
  const period = context.period.replace(/^(\d{2})(\d{2})Q([1-4])$/, "$3T$2");
  const entity = describeChatContext(context).split(" · ")[2];
  panel.querySelector<HTMLElement>("[data-chat-attachment-label]")!.textContent = context.filters?.map_scope
    ? describeChatContext(context) : card.classList.contains("narrative-card")
    ? `${title} · ${period}` : `${title} · ${entity} · ${period}`;
  attachment.title = describeChatContext(context);
  return context;
}

export function createChatAttachment(panel: HTMLElement, notice: HTMLElement) {
  let attachedContext: ChatContext | undefined;
  let officialDataset: string | undefined;
  const label = panel.querySelector<HTMLElement>("[data-chat-context]")!;
  const mapAvailable = () => Boolean(officialDataset && !officialState.loading && officialDataset === officialState.document?.dataset_version);

  function select(card?: Element): boolean {
    const useOfficialMap = mapAvailable();
    if (card && isOfficialMapCard(card) && !useOfficialMap) return false;
    attachedContext = attachChatCard(panel, card, useOfficialMap);
    label.textContent = attachedContext
      ? `Contexto: ${describeChatContext(attachedContext)}` : "Contexto: vista actual al enviar";
    return true;
  }

  function updateCapability(health: ChatHealth | undefined, refreshActions: () => void): void {
    officialDataset = Array.isArray(health?.enabled_capabilities) && health.enabled_capabilities.includes("official_route_queries")
      ? health.official_route_dataset_version : undefined;
    refreshActions();
    if (attachedContext?.filters?.map_scope && attachedContext.filters.map_dataset_version !== officialDataset) {
      select();
      notice.textContent = "Se quitó el mapa adjunto porque su versión no está disponible para el chat.";
    }
  }

  const contextForSend = () => structuredClone(attachedContext ?? buildChatContext(undefined, mapAvailable()));
  return { select, updateCapability, mapAvailable, contextForSend };
}
