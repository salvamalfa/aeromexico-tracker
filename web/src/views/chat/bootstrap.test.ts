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
let loseAcceptedPostResponse = false;
let acceptedRequests = new Map<string, { turn_id: string; status: string }>();
let postedBodies: Array<{ content: string; client_message_id: string; context: unknown }> = [];
let admittedTurnCount = 0;
let conversationMessages: Array<Record<string, unknown>> = [];
let conversationTurns: Array<{ id: string; status: string; error_message?: string }> = [];
let conversationReadError = false;
let conversationReadErrorStatus = 503;
let messagePostErrors: number[] = [];
let closeStreamAfterDelta = false;
let eventStreamUnavailable = false;
let eventStreamStatus = 503;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const frame = (seq: number, type: string, data: object) => enc.encode(`id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify(data)}\n\n`);

function installFetch(auth: "password" | "local") {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input); const method = init?.method ?? "GET";
    if (url.endsWith("/health")) return json({ status: "ok", auth, snapshot_version: "v1" });
    if (url.endsWith("/login")) return json({ session: "s-" + Math.random(), expires_at: "x" });
    if (url.endsWith("/conversations") && method === "POST") return json({ id: "c1", snapshot_version: "v1", created_at: "x" }, 201);
    if (url.includes("/conversations/c1/messages") && method === "POST") {
      const body = JSON.parse(String(init?.body)) as { content: string; client_message_id: string; context: unknown };
      postedBodies.push(body);
      const rejection = messagePostErrors.shift();
      if (rejection) return json({ detail: "login required" }, rejection);
      let result = acceptedRequests.get(body.client_message_id);
      if (!result) {
        admittedTurnCount += 1;
        result = { turn_id: "t1", status: "pending" };
        acceptedRequests.set(body.client_message_id, result);
        conversationMessages.push({ id: "accepted-user", role: "user", content: body.content, turn_id: result.turn_id, created_at: new Date().toISOString() });
        conversationTurns = [{ id: result.turn_id, status: conversationTurnStatus }];
      }
      if (loseAcceptedPostResponse) {
        loseAcceptedPostResponse = false;
        throw new TypeError("response lost after server acceptance");
      }
      return json(result, 202);
    }
    if (url.includes("/conversations/c1") && method === "DELETE") return deleteStatus === 204 ? new Response(null, { status: 204 }) : json({ detail: "boom" }, deleteStatus);
    if (url.includes("/conversations/c1")) {
      if (conversationReadError) return json({ detail: "temporary read failure" }, conversationReadErrorStatus);
      return json({ id: "c1", snapshot_version: "v1", messages: conversationMessages, turns: conversationTurns });
    }
    if (url.includes("/turns/t1/cancel")) {
      if (cancelStatus !== 200) return json({ detail: "login required" }, cancelStatus);
      conversationTurns = [{ id: "t1", status: "cancelled" }];
      return json({ status: "cancelled" });
    }
    if (url.includes("/turns/t1/events")) {
      if (eventStreamUnavailable) return json({ detail: "stream unavailable" }, eventStreamStatus);
      const body = new ReadableStream<Uint8Array>({ start(c) {
        streams.push(c);
        c.enqueue(frame(1, "turn.started", { status: "running" }));
        if (terminalEvent) { c.enqueue(frame(2, terminalEvent, { code: "provider_error" })); c.close(); return; }
        c.enqueue(frame(2, "message.delta", { text: "Hola" }));
        if (closeStreamAfterDelta) { c.close(); return; }
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
    loseAcceptedPostResponse = false; acceptedRequests = new Map(); postedBodies = []; admittedTurnCount = 0;
    conversationMessages = [{ id: "m1", role: "user", content: "hola", turn_id: "t1", created_at: "2020-01-01T00:00:00.000Z" }];
    conversationTurns = [{ id: "t1", status: conversationTurnStatus }];
    conversationReadError = false; conversationReadErrorStatus = 503; messagePostErrors = [];
    closeStreamAfterDelta = false; eventStreamUnavailable = false; eventStreamStatus = 503;
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

  it("shows the stored failure on its question after reopening without posting or replaying history", async () => {
    installFetch("local");
    localStorage.setItem("airline-tracker.chat.conversation-id", "c1");
    conversationMessages = [
      { id: "m-old", role: "user", content: "Pregunta anterior", turn_id: "t-old" },
      { id: "m-failed", role: "user", content: "¿Cuál fue la ocupación?", turn_id: "t-failed" },
    ];
    conversationTurns = [
      { id: "t-old", status: "completed" },
      { id: "t-failed", status: "failed", error_message: "No fue posible completar. <img src=x onerror=alert(1)>" },
    ];
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();

    const failedRow = panel.querySelector<HTMLElement>('[data-message-id="m-failed"]')!;
    expect(failedRow.dataset.turnId).toBe("t-failed");
    expect(failedRow.querySelector(".chat-failure")?.textContent).toContain("No fue posible completar.");
    expect(failedRow.querySelector("img")).toBeNull();
    expect(panel.querySelector('[data-message-id="m-old"] .chat-failure')).toBeNull();
    expect(panel.querySelector(".chat-message-assistant")).toBeNull();
    expect(panel.querySelector(".chat-retry")).toBeNull();
    expect(postedBodies).toHaveLength(0);
  });

  it("does not label a completed historical question as failed", async () => {
    installFetch("local");
    localStorage.setItem("airline-tracker.chat.conversation-id", "c1");
    conversationMessages = [{ id: "m1", role: "user", content: "Pregunta respondida", turn_id: "t1" }];
    conversationTurns = [{ id: "t1", status: "completed" }];
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();

    expect(panel.querySelector(".chat-failure")).toBeNull();
    expect(panel.querySelector(".chat-message-assistant")).toBeNull();
    expect(postedBodies).toHaveLength(0);
  });

  it("clears a prior failure when a refreshed conversation reports the turn completed", async () => {
    installFetch("password");
    localStorage.setItem("airline-tracker.chat.conversation-id", "c1");
    conversationMessages = [{ id: "m1", role: "user", content: "Pregunta guardada", turn_id: "t1" }];
    conversationTurns = [{ id: "t1", status: "failed", error_message: "No fue posible completar." }];
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const access = panel.querySelector<HTMLFormElement>("[data-chat-access]")!;
    const password = panel.querySelector<HTMLInputElement>("#chat-password")!;
    password.value = "secret"; access.requestSubmit(); await flush();
    expect(panel.querySelector(".chat-failure")?.textContent).toContain("No fue posible completar.");

    (panel.querySelector("[data-chat-logout]") as HTMLButtonElement).click(); await flush();
    conversationTurns = [{ id: "t1", status: "completed" }];
    password.value = "secret"; access.requestSubmit(); await flush();

    expect(panel.querySelector(".chat-failure")).toBeNull();
    expect(panel.querySelector(".chat-message-assistant")).toBeNull();
    expect(postedBodies).toHaveLength(0);
  });

  it("reuses the same client id and context when the accepted POST response is lost", async () => {
    installFetch("local");
    loseAcceptedPostResponse = true;
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const input = panel.querySelector("#chat-input") as HTMLTextAreaElement;
    input.value = "Compara el factor de ocupación";
    (panel.querySelector("[data-chat-form]") as HTMLFormElement).requestSubmit();
    await flush(50);

    expect(admittedTurnCount).toBe(1);
    expect(postedBodies).toHaveLength(1);
    expect(panel.querySelector("[data-chat-status]")?.textContent).toContain("resultado del envío es incierto");
    expect(panel.querySelector<HTMLButtonElement>("[data-chat-new]")?.disabled).toBe(true);
    expect(panel.querySelector(".chat-retry")).not.toBeNull();

    terminalEvent = "turn.completed";
    (panel.querySelector(".chat-retry") as HTMLButtonElement).click();
    await flush(80);

    expect(postedBodies).toHaveLength(2);
    expect(postedBodies[1]?.client_message_id).toBe(postedBodies[0]?.client_message_id);
    expect(postedBodies[1]?.content).toBe(postedBodies[0]?.content);
    expect(postedBodies[1]?.context).toEqual(postedBodies[0]?.context);
    expect(admittedTurnCount).toBe(1);
    expect(panel.querySelector("[data-chat-status]")?.textContent).toBe("Respuesta completa.");
  });

  it("preserves an unresolved key across retry 401 and an identical older message on re-login", async () => {
    installFetch("password");
    loseAcceptedPostResponse = true;
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const access = panel.querySelector<HTMLFormElement>("[data-chat-access]")!;
    const password = panel.querySelector<HTMLInputElement>("#chat-password")!;
    password.value = "correct-horse-battery"; access.requestSubmit(); await flush();
    const input = panel.querySelector<HTMLTextAreaElement>("#chat-input")!;
    input.value = "hola"; panel.querySelector<HTMLFormElement>("[data-chat-form]")!.requestSubmit(); await flush(50);
    const originalKey = postedBodies[0]?.client_message_id;

    messagePostErrors.push(401);
    (panel.querySelector(".chat-retry") as HTMLButtonElement).click(); await flush();
    expect(access.hidden).toBe(false);
    expect(postedBodies[1]?.client_message_id).toBe(originalKey);

    conversationTurnStatus = "completed";
    conversationTurns = [{ id: "t1", status: "completed" }];
    password.value = "correct-horse-battery"; access.requestSubmit(); await flush(50);
    expect(panel.querySelector<HTMLButtonElement>("[data-chat-send]")?.disabled).toBe(true);
    expect(panel.querySelector(".chat-retry")).not.toBeNull();

    terminalEvent = "turn.completed";
    (panel.querySelector(".chat-retry") as HTMLButtonElement).click(); await flush(80);
    expect(postedBodies).toHaveLength(3);
    expect(postedBodies.map((body) => body.client_message_id)).toEqual([originalKey, originalKey, originalKey]);
    expect(postedBodies[2]?.context).toEqual(postedBodies[0]?.context);
    expect(admittedTurnCount).toBe(1);
  });

  it("keeps the original turn key when SSE and conversation reconciliation are unavailable", async () => {
    installFetch("local");
    eventStreamUnavailable = true;
    conversationReadError = true;
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const input = panel.querySelector<HTMLTextAreaElement>("#chat-input")!;
    input.value = "Compara la ocupación";
    panel.querySelector<HTMLFormElement>("[data-chat-form]")!.requestSubmit();
    await flush(4200);

    expect(admittedTurnCount).toBe(1);
    expect(panel.querySelector<HTMLButtonElement>("[data-chat-send]")?.disabled).toBe(true);
    expect(panel.querySelector(".chat-retry")).not.toBeNull();
    const originalKey = postedBodies[0]?.client_message_id;

    conversationReadError = false;
    eventStreamUnavailable = false;
    terminalEvent = "turn.completed";
    (panel.querySelector(".chat-retry") as HTMLButtonElement).click(); await flush(80);
    expect(postedBodies).toHaveLength(2);
    expect(postedBodies[1]?.client_message_id).toBe(originalKey);
    expect(admittedTurnCount).toBe(1);
    expect(panel.querySelector("[data-chat-status]")?.textContent).toBe("Respuesta completa.");
  });

  it("unlocks controls when re-login reconciles an exact terminal turn after SSE 401", async () => {
    installFetch("password");
    const { mountChat } = await import("./bootstrap");
    disposeChat = mountChat();
    const panel = document.getElementById("airline-chat-panel")!;
    (document.querySelector(".chat-launcher") as HTMLButtonElement).click(); await flush();
    const access = panel.querySelector<HTMLFormElement>("[data-chat-access]")!;
    const password = panel.querySelector<HTMLInputElement>("#chat-password")!;
    password.value = "correct-horse-battery"; access.requestSubmit(); await flush();
    eventStreamUnavailable = true; eventStreamStatus = 401;
    conversationReadError = true; conversationReadErrorStatus = 401;
    const input = panel.querySelector<HTMLTextAreaElement>("#chat-input")!;
    input.value = "Verifica el factor";
    panel.querySelector<HTMLFormElement>("[data-chat-form]")!.requestSubmit(); await flush(80);
    expect(access.hidden).toBe(false);
    expect(postedBodies).toHaveLength(1);

    eventStreamUnavailable = false; conversationReadError = false;
    conversationTurns = [{ id: "t1", status: "completed" }];
    password.value = "correct-horse-battery"; access.requestSubmit(); await flush(80);

    expect(panel.querySelector<HTMLButtonElement>("[data-chat-send]")?.disabled).toBe(false);
    expect(panel.querySelector<HTMLButtonElement>("[data-chat-new]")?.disabled).toBe(false);
    expect(postedBodies).toHaveLength(1);
    expect(admittedTurnCount).toBe(1);
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
