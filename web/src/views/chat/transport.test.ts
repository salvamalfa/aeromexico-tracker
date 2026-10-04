import { describe, expect, it, vi } from "vitest";
import { ChatApiError, ChatTransport, normalizeApiUrl } from "./transport";

describe("normalizeApiUrl", () => {
  it("defaults to the same-origin API and accepts secure remote URLs", () => {
    expect(normalizeApiUrl("")).toBe("/api/chat");
    expect(normalizeApiUrl("/api/chat/")).toBe("/api/chat");
    expect(normalizeApiUrl("https://chat.example.org/api/chat")).toBe("https://chat.example.org/api/chat");
    expect(normalizeApiUrl("http://localhost:8000/api/chat")).toBe("http://localhost:8000/api/chat");
  });

  it("rejects public insecure URLs, embedded credentials, query parameters, and protocol-relative URLs", () => {
    for (const url of ["http://chat.example.org", "//evil.example/api", "https://user:secret@example.org", "https://example.org?token=secret", "javascript:alert(1)"]) {
      expect(() => normalizeApiUrl(url)).toThrow();
    }
  });
});

describe("ChatTransport", () => {
  it("sends the structured context and bearer token only in the request", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify({ turn_id: "turn-1", status: "queued" }), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    const api = new ChatTransport("/api/chat", () => "session-token", fetcher as typeof fetch);
    const context = { tab: "economy" as const, period: "2026Q2", entity: ["INDUSTRY"], card_id: "unit-chart", filters: { range: "12" as const } };
    const result = await api.sendMessage("conversation/a", "¿Cómo cambió?", context, "client-1");
    expect(result.turn_id).toBe("turn-1");
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0]!;
    expect(url).toBe("/api/chat/conversations/conversation%2Fa/messages");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer session-token");
    expect(JSON.parse(String(init?.body))).toEqual({ content: "¿Cómo cambió?", client_message_id: "client-1", context });
  });

  it("replays ordered SSE events after the last sequence and ignores duplicates", async () => {
    const source = [
      "id: 1\nevent: message.delta\ndata: {\"turn_id\":\"t\",\"text\":\"a\"}\n\n",
      "id: 1\nevent: message.delta\ndata: {\"turn_id\":\"t\",\"text\":\"duplicate\"}\n\n",
      "id: 2\nevent: turn.completed\ndata: {\"turn_id\":\"t\"}\n\n",
    ].join("");
    const fetcher = vi.fn(async (_url: RequestInfo | URL) => new Response(new ReadableStream({
      start(controller) { controller.enqueue(new TextEncoder().encode(source)); controller.close(); },
    }), { status: 200, headers: { "Content-Type": "text/event-stream" } }));
    const api = new ChatTransport("https://chat.example.org/api/chat", undefined, fetcher as typeof fetch);
    const seen: string[] = [];
    const last = await api.streamEvents("turn id", 0, new AbortController().signal, (event) => seen.push(event.type));
    expect(fetcher.mock.calls[0]?.[0]).toBe("https://chat.example.org/api/chat/turns/turn%20id/events?after=0");
    expect(seen).toEqual(["message.delta", "turn.completed"]);
    expect(last).toBe(2);
  });

  it("rejects malformed event objects instead of rendering them", async () => {
    const source = "id: 1\nevent: message.delta\ndata: []\n\n";
    const fetcher = async () => new Response(source, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    const api = new ChatTransport("/api/chat", undefined, fetcher as typeof fetch);
    await expect(api.streamEvents("turn", 0, new AbortController().signal, () => undefined)).rejects.toBeInstanceOf(ChatApiError);
  });
});
