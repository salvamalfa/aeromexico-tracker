// Clickable source details, available with mouse, keyboard and touch. Keep
// the panel outside its heading so card labels contain only the visible title.
export const AFAC_CATALOG_URL = "https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404";

export function setAfacSource(panel: HTMLElement, detail: string): void {
  const source = document.createElement("b");
  const link = document.createElement("a");
  link.href = AFAC_CATALOG_URL; link.textContent = "AFAC";
  link.target = "_blank"; link.rel = "noopener noreferrer";
  source.append(document.createTextNode("Fuente: "),link,document.createTextNode(". "));
  panel.replaceChildren(source, document.createTextNode(detail));
}

interface ActiveInfo { button: HTMLElement; panel: HTMLElement; close: () => void; }
let active: ActiveInfo | undefined;
let documentBound = false;
const bound = new WeakSet<HTMLElement>();

export function closeSourceInfoWithin(root: Element): void {
  if (active && (root.contains(active.button) || root.contains(active.panel))) active.close();
}

export function bindSourceInfo(button: HTMLElement, panel: HTMLElement): void {
  if (bound.has(button)) return;
  bound.add(button);
  button.setAttribute("aria-controls", panel.id);
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-describedby", panel.id);
  panel.setAttribute("popover", "manual");
  panel.classList.add("market-source-note");
  let open = false, pinned = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const cancelClose = () => { if (timer) clearTimeout(timer); };
  const close = () => {
    cancelClose(); pinned = false; open = false;
    if (panel.hidePopover) panel.hidePopover();
    delete panel.dataset.open;
    button.setAttribute("aria-expanded", "false");
    if (active?.button === button) active = undefined;
  };
  const show = () => {
    cancelClose();
    if (open) return;
    active?.close(); active = {button,panel,close}; open = true;
    if (panel.showPopover) panel.showPopover();
    panel.dataset.open = "true";
    button.setAttribute("aria-expanded", "true");
    const anchor = button.getBoundingClientRect(), box = panel.getBoundingClientRect();
    const width=document.documentElement.clientWidth||window.innerWidth;
    const height=document.documentElement.clientHeight||window.innerHeight;
    panel.style.left = `${Math.max(12, Math.min(anchor.left, width - box.width - 12))}px`;
    panel.style.top = `${Math.max(12, Math.min(anchor.bottom + 8, height - box.height - 12))}px`;
  };
  const scheduleClose = () => {
    cancelClose();
    timer = setTimeout(() => {
      if (!pinned && !panel.contains(document.activeElement) && document.activeElement !== button) close();
    }, 180);
  };
  button.addEventListener("pointerenter", event => { if (event.pointerType !== "touch") show(); });
  button.addEventListener("pointerleave", scheduleClose);
  button.addEventListener("focus", show);
  button.addEventListener("blur", scheduleClose);
  button.addEventListener("click", event => {
    event.preventDefault();
    if (pinned) close(); else { show(); pinned = true; }
  });
  panel.addEventListener("pointerenter", cancelClose);
  panel.addEventListener("pointerleave", scheduleClose);
  panel.addEventListener("focusin", cancelClose);
  panel.addEventListener("focusout", scheduleClose);
  if (!documentBound) {
    documentBound = true;
    window.addEventListener("reader-tab-visible", () => active?.close());
    window.addEventListener("resize", () => active?.close());
    document.addEventListener("pointerdown", event => {
      if (active && !active.panel.contains(event.target as Node) && !active.button.contains(event.target as Node)) active.close();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && active) {
        const button = active.button;
        active.close(); button.focus();
        // Focus opens details; Escape must still leave them dismissed.
        active?.close();
      }
    });
  }
}
