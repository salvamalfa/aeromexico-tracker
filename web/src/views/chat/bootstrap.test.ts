import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/plotly", () => ({ default: { newPlot: () => Promise.resolve(), Plots: { resize: () => Promise.resolve() } } }));

const enc = new TextEncoder();
const flush = (ms = 20) => new Promise((r) => setTimeout(r, ms));
type Ctl = ReadableStreamDefaultController<Uint8Array>;
const streams: Ctl[] = [];
let conversationTurnStatus = "running";
let cancelStatus = 401;
let deleteStatus = 204;
let terminalEvent: string | undefined;
let disposeChat: (() => void) | undefined;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const frame = (seq: number, type: string, data: object) => enc.encode(`id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`);

function installFetch(auth: "password" | "local") {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); const method = init?.method ?? "GET";
    if (url.endsWith("/health")) return json({ status: "ok", auth, snapshot_version: "v1" });
    if (url.endsWith("/login")) return json({ session: "s-" + Math.random(), expires_at: "x" });
    if (url.endsWith("/conversations") && method === "POST") return json({ id: "c1", snapshot_version: "v1", created_at: "x" }, 201);
    if (url.includes("/conversations/c1/messages")) return json({ turn_id: "t1", status: "pending" }, 202);
    if (url.includes("/conversations/c1") && method === "DELETE") return deleteStatus === 204 ? new Response(null, { status: 204 }) : json({ detail: "boom" }, deleteStatus);
    if (url.includes("/conversations/c1")) return json({ id: "c1", snapshot_version: "v1", messages: [{ id: "m1", role: "user", content: "hola", turn_id: "t1" }], turns: [{ id: "t1", status: conversationTurnStatus }] });
    if (url.includes("/turns/t1/cancel")) return cancelStatus === 200 ? json({ status: "cancelled" }) : json({ detail: "login required" }, cancelStatus);
    if (url.includes("/turns/t1/events")) {
      const body = new ReadableStream<Uint8Array>({ start(c) {
        streams.push(c);
        c.enqueue(frame(1, "turn.started", { status: "running" }));
        if (terminalEvent) { c.enqueue(frame(2, terminalEvent, { code: "provider_error" })); c.close(); return; }
        c.enqueue(frame(2, "message.delta", { text: "Hola" }));
      } });
      return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    }
    throw new Error("unexpected " + method + " " + url);
  }) as typeof fetch;
}

describe("chat bootstrap audit", () => {
  afterEach(() => {
    disposeChat?.();
    disposeChat = undefined;
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    document.body.innerHTML = ""; streams.length = 0; localStorage.clear(); vi.resetModules();
    conversationTurnStatus = "running"; cancelStatus = 401; deleteStatus = 204; terminalEvent = undefined;
  });

  it("does not run two listeners after a 401 on cancel and re-login", async () => {
    installFetch("password"); cancelStatus = 401;
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const access = panel.querySelector("[data-chat-access]") as HTMLFormElement;
    const pw = panel.querySelector("#chat-password") as HTMLInputElement;
    pw.value = "correct-horse-battery"; access.requestSubmit(); await flush();
    const input = panel.querySelector("#chat-input") as HTMLTextAreaElement;
    input.value = "hola"; (panel.querySelector("[data-chat-form]") as HTMLFormElement).requestSubmit(); await flush(50);
    expect(streams.length).toBe(1);
    (panel.querySelector("[data-chat-cancel]") as HTMLButtonElement).click(); await flush();
    expect(access.hidden).toBe(false);
    pw.value = "correct-horse-battery"; access.requestSubmit(); await flush(50);
    for (const c of streams) c.enqueue(frame(3, "message.delta", { text: " mundo" }));
    await flush(50);
    const text = [...panel.querySelectorAll(".chat-message-assistant .chat-message-body")].map((n) => n.textContent).join("|");
    expect(text).toBe("Hola mundo");
  });

  it("does not stay busy when deleting a conversation fails during an active turn", async () => {
    installFetch("local"); cancelStatus = 200; deleteStatus = 500;
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const input = panel.querySelector("#chat-input") as HTMLTextAreaElement;
    input.value = "hola"; (panel.querySelector("[data-chat-form]") as HTMLFormElement).requestSubmit(); await flush(50);
    (panel.querySelector("[data-chat-delete]") as HTMLButtonElement).click(); await flush(50);
    // the server already appended turn.cancelled, but the aborted client never reads it
    expect(input.disabled).toBe(false);
  });

  it("double-clicking the launcher while a turn is running does not open two streams", async () => {
    installFetch("local"); conversationTurnStatus = "running";
    localStorage.setItem("airline-tracker.chat.conversation-id", "c1");
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const launcher = document.querySelector(".chat-launcher") as HTMLButtonElement;
    launcher.click(); launcher.click(); await flush(50);
    expect(streams.length).toBe(1);
  });

  it("a failed turn without text still offers Reintentar", async () => {
    installFetch("local"); terminalEvent = "turn.failed";
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const input = panel.querySelector("#chat-input") as HTMLTextAreaElement;
    input.value = "hola"; (panel.querySelector("[data-chat-form]") as HTMLFormElement).requestSubmit(); await flush(50);
    expect(panel.querySelector(".chat-retry")).not.toBeNull();
    expect(input.disabled).toBe(false);
  });

  it("logout keeps the stored conversation for the next login", async () => {
    installFetch("password");
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const pw = panel.querySelector("#chat-password") as HTMLInputElement;
    pw.value = "correct-horse-battery"; (panel.querySelector("[data-chat-access]") as HTMLFormElement).requestSubmit(); await flush();
    expect(localStorage.getItem("airline-tracker.chat.conversation-id")).toBe("c1");
    (panel.querySelector("[data-chat-logout]") as HTMLButtonElement).click(); await flush();
    expect(localStorage.getItem("airline-tracker.chat.conversation-id")).toBe("c1");
    expect((panel.querySelector("[data-chat-access]") as HTMLFormElement).hidden).toBe(false);
  });

  it("uses a mobile modal and returns focus to the card opener", async () => {
    installFetch("local");
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const pageShell = document.createElement("main");
    pageShell.className = "page-shell";
    const card = document.createElement("section");
    card.className = "chart-card";
    pageShell.append(card);
    document.body.append(pageShell);

    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const opener = card.querySelector<HTMLButtonElement>(".chat-card-action")!;
    opener.click();
    await flush();

    const panel = document.getElementById("airline-chat-panel")!;
    const launcher = document.querySelector<HTMLButtonElement>(".chat-launcher")!;
    expect(panel.getAttribute("role")).toBe("dialog");
    expect(panel.getAttribute("aria-modal")).toBe("true");
    expect(pageShell.inert).toBe(true);
    expect(launcher.inert).toBe(true);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(panel.hidden).toBe(true);
    expect(pageShell.inert).toBe(false);
    expect(launcher.inert).toBe(false);
    expect(document.activeElement).toBe(opener);
  });
});
