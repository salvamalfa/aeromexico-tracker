export const CHAT_OVERLAY_QUERY = "(max-width: 1000px)";

export interface ChatModalControls {
  open(opener?: HTMLElement): void;
  close(): void;
  dispose(): void;
}

export function mountChatModal(
  panel: HTMLElement,
  launcher: HTMLElement,
  background: HTMLElement | null,
): ChatModalControls {
  let open = false;
  let focusReturn: HTMLElement | null = null;
  let inertApplied = false;
  let previousBackgroundInert = false;
  let previousLauncherInert = false;

  const mobile = () => window.matchMedia?.(CHAT_OVERLAY_QUERY).matches ?? window.innerWidth <= 1000;
  const restoreInert = () => {
    if (!inertApplied) return;
    if (background) background.inert = previousBackgroundInert;
    launcher.inert = previousLauncherInert;
    inertApplied = false;
  };
  const syncMode = () => {
    if (!open || !mobile()) {
      panel.removeAttribute("role");
      panel.removeAttribute("aria-modal");
      restoreInert();
      return;
    }
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    if (!inertApplied) {
      previousBackgroundInert = background?.inert === true;
      previousLauncherInert = launcher.inert === true;
      if (background) background.inert = true;
      launcher.inert = true;
      inertApplied = true;
    }
    if (!panel.contains(document.activeElement)) panel.querySelector<HTMLElement>("[data-chat-close]")?.focus({ preventScroll: true });
  };

  return {
    open(opener?: HTMLElement) {
      if (opener?.isConnected) focusReturn = opener;
      if (!open) {
        const active = document.activeElement;
        focusReturn ??= active instanceof HTMLElement ? active : launcher;
        open = true;
        window.addEventListener("resize", syncMode);
      }
      syncMode();
    },
    close() {
      open = false;
      window.removeEventListener("resize", syncMode);
      syncMode();
      const target = focusReturn?.isConnected ? focusReturn : launcher;
      focusReturn = null;
      target.focus();
    },
    dispose() {
      open = false;
      window.removeEventListener("resize", syncMode);
      syncMode();
      focusReturn = null;
    },
  };
}
