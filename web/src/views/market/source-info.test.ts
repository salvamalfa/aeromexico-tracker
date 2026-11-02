import { afterEach, expect, it, vi } from "vitest";
import { AFAC_CATALOG_URL, bindSourceInfo, closeSourceInfoWithin, setAfacSource } from "./source-info";
import { chatCardLabel } from "../chat/card-actions";

afterEach(() => { vi.useRealTimers(); document.body.replaceChildren(); });
function fixture() {
  document.body.innerHTML = '<div class="kpi-card"><p class="kpi-label">Cambio interanual<button class="market-source-info" id="info">ⓘ</button></p><div id="source"></div></div>';
  const button = document.getElementById("info")!, panel = document.getElementById("source")!;
  setAfacSource(panel,"Cálculo con los mismos meses del año anterior."); bindSourceInfo(button,panel);
  return {button,panel};
}

it("offers an actual source link outside the heading and preserves the attachment title", () => {
  const {button,panel} = fixture();
  expect(panel.textContent).toContain("Fuente: AFAC.");
  expect(panel.querySelector("a")?.href).toBe(AFAC_CATALOG_URL);
  expect(panel.querySelector("a")?.textContent).toBe("AFAC");
  expect(panel.querySelector("b")?.textContent).toBe("Fuente: AFAC. ");
  expect(panel.querySelectorAll("a")).toHaveLength(1);
  expect(panel.querySelector("a")?.rel).toBe("noopener noreferrer");
  expect(button.getAttribute("aria-controls")).toBe(panel.id);
  expect(button.getAttribute("aria-describedby")).toBe(panel.id);
  expect(button.hasAttribute("title")).toBe(false);
  expect(chatCardLabel(document.querySelector(".kpi-card")!)).toBe("Cambio interanual");
});

it("opens on keyboard focus, pins on touch/click and dismisses on Escape or an outside click", () => {
  const {button,panel} = fixture();
  button.tabIndex = 0; button.focus();
  expect(button.getAttribute("aria-expanded")).toBe("true");
  button.click(); expect(panel.dataset.open).toBe("true");
  document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}));
  expect(button.getAttribute("aria-expanded")).toBe("false");
  button.click(); expect(panel.dataset.open).toBe("true");
  document.body.dispatchEvent(new Event("pointerdown",{bubbles:true}));
  expect(button.getAttribute("aria-expanded")).toBe("false");
});

it("keeps the panel open while moving the pointer to its clickable source link", () => {
  vi.useFakeTimers();
  const {button,panel} = fixture();
  button.dispatchEvent(new Event("pointerenter"));
  button.dispatchEvent(new Event("pointerleave"));
  panel.dispatchEvent(new Event("pointerenter"));
  vi.advanceTimersByTime(200);
  expect(panel.dataset.open).toBe("true");
  panel.dispatchEvent(new Event("pointerleave")); vi.advanceTimersByTime(200);
  expect(button.getAttribute("aria-expanded")).toBe("false");
});

it("closes an open panel before its host is replaced, leaving unrelated hosts untouched",()=>{
  const {button,panel}=fixture();
  button.click();
  closeSourceInfoWithin(document.createElement("div"));
  expect(panel.dataset.open).toBe("true");
  closeSourceInfoWithin(button.closest(".kpi-card")!);
  expect(panel.dataset.open).toBeUndefined();
  expect(button.getAttribute("aria-expanded")).toBe("false");
});

it("dismisses a source panel when changing dashboard tabs",()=>{
  const {button,panel}=fixture(); button.click();
  window.dispatchEvent(new CustomEvent("reader-tab-visible",{detail:{panelId:"panel-economy"}}));
  expect(panel.dataset.open).toBeUndefined();
  expect(button.getAttribute("aria-expanded")).toBe("false");
});

it("dismisses an open source panel before a viewport resize can leave it outside the screen",()=>{
  const {button,panel}=fixture();button.click();
  window.dispatchEvent(new Event("resize"));
  expect(panel.dataset.open).toBeUndefined();expect(button.getAttribute("aria-expanded")).toBe("false");
});
