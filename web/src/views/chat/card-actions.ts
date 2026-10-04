export function mountChatCardActions(
  openChat: (card: Element, opener: HTMLElement) => void,
  onCardFocus: (card: Element) => void,
): () => void {
  const cardButton = (card: HTMLElement, label: string) => {
    if (card.querySelector(":scope > .chat-card-action")) return;
    card.classList.add("chat-card-host");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-card-action";
    button.textContent = "Preguntar a Airline Tracker";
    button.setAttribute("aria-label", `Preguntar sobre ${label}`);
    button.addEventListener("click", () => openChat(card, button));
    card.append(button);
  };
  const bindCardActions = () => {
    document.querySelectorAll<HTMLElement>(".chart-card, .kpi-card, .flight-kpi, .narrative-card").forEach((card) => {
      const title = card.querySelector<HTMLElement>(".chart-title")?.textContent?.trim() ?? "esta gráfica";
      cardButton(card, title);
    });
    document.querySelectorAll<HTMLElement>(".flights-shell").forEach((card) => cardButton(card, "la vista de vuelos"));
  };
  const onCardEvent = (event: Event) => {
    const card = (event.target as Element | null)?.closest?.(".chart-card, .flights-shell, .kpi-card");
    if (card) onCardFocus(card);
  };

  bindCardActions();
  const observer = new MutationObserver(bindCardActions);
  observer.observe(document.querySelector(".page-shell") ?? document.body, { childList: true, subtree: true });
  window.addEventListener("reader-tab-visible", bindCardActions);
  document.addEventListener("click", onCardEvent, true);
  document.addEventListener("focusin", onCardEvent, true);

  return () => {
    observer.disconnect();
    window.removeEventListener("reader-tab-visible", bindCardActions);
    document.removeEventListener("click", onCardEvent, true);
    document.removeEventListener("focusin", onCardEvent, true);
    document.querySelectorAll(".chat-card-action").forEach((button) => button.remove());
    document.querySelectorAll(".chat-card-host").forEach((card) => card.classList.remove("chat-card-host"));
  };
}
