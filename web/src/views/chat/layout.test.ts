import { afterEach, describe, expect, it, vi } from "vitest";
import { mountChatLayout } from "./layout";

afterEach(() => { document.body.innerHTML = ""; vi.unstubAllGlobals(); });

describe("adjacent chat layout", () => {
  it("groups the dashboard with its rail and restores the original document on disposal", () => {
    document.body.innerHTML = '<main class="page-shell"><header><div class="hero-grid"><h1>Tracker</h1><div class="period-control">Trimestre</div></div></header><div class="reader-tabs" role="tablist"></div><section>Lectura</section></main>';
    const main = document.querySelector<HTMLElement>("main")!;
    const period = document.querySelector(".period-control")!;
    const tabs = document.querySelector(".reader-tabs")!;
    const panel = document.createElement("aside"); panel.id = "chat-panel";
    const layout = mountChatLayout(panel);
    const workspace = document.querySelector(".dashboard-workspace")!;
    expect([...workspace.children]).toEqual([main, panel.parentElement]);
    expect(panel.parentElement?.className).toBe("chat-column");
    expect([...document.querySelector(".reader-tabs-row")!.children]).toEqual([tabs, layout.launcher]);
    expect(layout.launcher.getAttribute("aria-label")).toBe("Abrir chat");
    expect(layout.launcher.textContent).toBe("");
    expect(tabs.contains(layout.launcher)).toBe(false);
    expect(layout.launcher.getAttribute("aria-controls")).toBe(panel.id);
    layout.dispose();
    expect(document.body.children).toHaveLength(1);
    expect(document.body.firstElementChild).toBe(main);
    expect(document.querySelector(".reader-tabs-row")).toBeNull();
    expect(period.parentElement?.className).toBe("hero-grid");
  });

  it("tracks the dashboard's natural height as views and their contents change", () => {
    let onResize: (() => void) | undefined;
    const disconnect = vi.fn(); const observe = vi.fn();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: () => void) { onResize = callback; }
      observe = observe;
      disconnect = disconnect;
    });
    document.body.innerHTML = '<main class="page-shell"></main>';
    const main = document.querySelector<HTMLElement>("main")!;
    let height = 420;
    vi.spyOn(main, "getBoundingClientRect").mockImplementation(() => ({ height } as DOMRect));
    const layout = mountChatLayout(document.createElement("aside"));
    const workspace = document.querySelector<HTMLElement>(".dashboard-workspace")!;
    expect(observe).toHaveBeenCalledWith(main);
    expect(workspace.style.getPropertyValue("--dashboard-content-height")).toBe("420px");
    height = 260; onResize?.();
    expect(workspace.style.getPropertyValue("--dashboard-content-height")).toBe("260px");
    layout.dispose();
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
