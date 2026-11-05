/** Keep the conversation beside the dashboard, within its scroll boundaries. */
export function mountChatLayout(panel: HTMLElement) {
  const focused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "chat-launcher";
  launcher.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3m.08 4h.01"/></svg>';
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", panel.id);
  launcher.setAttribute("aria-label", "Abrir chat");
  launcher.title = "Abrir chat";
  const background = document.querySelector<HTMLElement>(".page-shell");
  const tabs = background?.querySelector<HTMLElement>(".reader-tabs");
  const tabsRow = document.createElement("div");
  tabsRow.className = "reader-tabs-row";
  if (tabs) { tabs.before(tabsRow); tabsRow.append(tabs, launcher); }
  else (background ?? document.body).append(launcher);

  const workspace = document.createElement("div");
  workspace.className = "dashboard-workspace";
  const column = document.createElement("div");
  column.className = "chat-column";
  if (background) {
    background.before(workspace);
    workspace.append(background, column);
    column.append(panel);
  } else document.body.append(panel);

  const syncHeight = () => {
    if (background) workspace.style.setProperty("--dashboard-content-height", `${background.getBoundingClientRect().height}px`);
  };
  const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(syncHeight);
  if (background) observer?.observe(background);
  window.addEventListener("resize", syncHeight);
  syncHeight();
  if (focused?.isConnected && focused !== document.body) focused.focus({ preventScroll: true });
  return {
    launcher, background,
    dispose() {
      observer?.disconnect();
      window.removeEventListener("resize", syncHeight);
      if (tabs && tabsRow.isConnected) tabsRow.before(tabs);
      tabsRow.remove();
      launcher.remove();
      panel.remove();
      if (background && workspace.isConnected) workspace.replaceWith(background);
    },
  };
}
