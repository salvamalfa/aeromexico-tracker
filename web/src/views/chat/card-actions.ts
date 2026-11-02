export function chatCardLabel(card: Element): string {
  if (card.classList.contains("narrative-card")) return "Lectura ejecutiva";
  if (card.id === "map-panel") return "Mapa de rutas";
  const title = card.querySelector(".chart-title, .panel-title, .kpi-label, h2, h3, :scope > p")?.cloneNode(true) as Element | undefined;
  title?.querySelectorAll(".kpi-info, .info, .market-source-info, .source-note, sup").forEach(node => node.remove());
  return title?.textContent?.trim() || "esta tarjeta";
}

export function mountChatCardActions(
  openChat: (card: Element, opener: HTMLElement) => void,
): () => void {
  const cardButton = (card: HTMLElement, label: string) => {
    if (card.hasAttribute("data-chat-unavailable")) return;
    const existing = card.querySelector<HTMLButtonElement>(":scope > .chat-card-action");
    if (existing) {
      existing.setAttribute("aria-label", `Preguntar sobre ${label}`);
      return;
    }
    card.classList.add("chat-card-host");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-card-action";
    button.textContent = "Pregunta";
    button.setAttribute("aria-label", `Preguntar sobre ${label}`);
    button.addEventListener("click", () => openChat(card, button));
    card.append(button);
  };
  const bindCardActions = () => {
    document.querySelectorAll<HTMLElement>(".chart-card, .kpi-card, .flight-kpi, .narrative-card, .flights-view .panel.chart-panel, .flights-view .panel.flow-map-panel, #news-heading").forEach((card) => {
      if (card.matches(".kpi-card, .flight-kpi")) {
        const label = card.querySelector(".kpi-label, :scope > p");
        const info = card.querySelector(":scope > .kpi-info, :scope > .info");
        if (label && info) {
          info.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor"/><circle cx="8" cy="4.8" r=".8" fill="currentColor"/><path d="M8 7v4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';
          label.append(info);
        }
      }
      cardButton(card, chatCardLabel(card));
    });
  };

  bindCardActions();
  const observer = new MutationObserver(bindCardActions);
  observer.observe(document.querySelector(".page-shell") ?? document.body, { childList: true, subtree: true });
  window.addEventListener("reader-tab-visible", bindCardActions);

  return () => {
    observer.disconnect();
    window.removeEventListener("reader-tab-visible", bindCardActions);
    document.querySelectorAll(".chat-card-action").forEach((button) => button.remove());
    document.querySelectorAll(".chat-card-host").forEach((card) => {
      if (card.matches(".kpi-card, .flight-kpi")) {
        const info = card.querySelector(":scope > p > .kpi-info, :scope > p > .info");
        if (info) { info.textContent = "i"; card.prepend(info); }
      }
      card.classList.remove("chat-card-host");
    });
  };
}
