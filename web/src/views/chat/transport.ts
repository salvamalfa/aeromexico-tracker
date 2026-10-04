import type { ChatConversation, ChatContext, ChatEvent } from "../../types/chat";

export class ChatApiError extends Error {
  constructor(message: string, readonly status?: number, readonly retryAfterSeconds?: number) {
    super(message);
    this.name = "ChatApiError";
  }
}

export function normalizeApiUrl(raw: string): string {
  const value = raw.trim().replace(/\/+$/, "");
  if (!value) return "/api/chat";
  if (value.includes("\\") || value.startsWith("//") || value.includes("#") || value.includes("?")) {
    throw new Error("VITE_CHAT_API_URL no puede incluir credenciales, query, fragmento ni una ruta protocol-relative.");
  }
  if (value.startsWith("/")) return value;
  let parsed: URL;
  try { parsed = new URL(value); } catch { throw new Error("VITE_CHAT_API_URL debe ser una URL HTTP(S) o una ruta local."); }
  const localHost = ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && localHost)) throw new Error("La URL del chat debe usar HTTPS (HTTP solo en loopback local).");
  if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error("VITE_CHAT_API_URL no debe incluir credenciales, query ni fragmento.");
  return value;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `El servicio respondió HTTP ${response.status}.`;
    try {
      const body = await response.json() as { detail?: unknown; message?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (typeof body.message === "string") message = body.message;
    } catch { /* use the status message */ }
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ChatApiError(message, response.status, Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined);
  }
  return response.json() as Promise<T>;
}

export class ChatTransport {
  readonly baseUrl: string;
  private readonly tokenProvider?: () => string | undefined;
  private readonly fetcher: typeof fetch;

  constructor(baseUrl: string, tokenProvider?: () => string | undefined, fetcher?: typeof fetch) {
    this.baseUrl = normalizeApiUrl(baseUrl);
    this.tokenProvider = tokenProvider;
    this.fetcher = fetcher ?? ((input, init) => globalThis.fetch(input, init));
  }

  private headers(extra: HeadersInit = {}): Headers {
    const headers = new Headers(extra);
    const token = this.tokenProvider?.();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return headers;
  }

  private async json<T>(path: string, init: RequestInit = {}): Promise<T> {
    return parseResponse<T>(await this.fetcher(`${this.baseUrl}${path}`, {
      ...init,
      headers: this.headers({ "Content-Type": "application/json", ...init.headers }),
    }));
  }

  health(): Promise<{ status?: string; snapshot_version?: string; auth?: "local" | "password" }> { return this.json("/health"); }
  login(password: string): Promise<{ session: string; expires_at: string }> {
    return this.json("/login", { method: "POST", body: JSON.stringify({ password }) });
  }
  async logout(): Promise<void> {
    const response = await this.fetcher(`${this.baseUrl}/logout`, { method: "POST", body: "{}", headers: this.headers({ "Content-Type": "application/json" }) });
    if (!response.ok) await parseResponse(response);
  }
  createConversation(): Promise<{ id: string; snapshot_version: string; created_at: string }> {
    return this.json("/conversations", { method: "POST", body: "{}" });
  }
  conversation(id: string): Promise<ChatConversation> { return this.json(`/conversations/${encodeURIComponent(id)}`); }
  async deleteConversation(id: string): Promise<void> {
    const response = await this.fetcher(`${this.baseUrl}/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE", headers: this.headers(),
    });
    if (!response.ok) await parseResponse(response);
  }
  sendMessage(id: string, content: string, context: ChatContext, clientMessageId: string): Promise<{ turn_id: string; status: string }> {
    return this.json(`/conversations/${encodeURIComponent(id)}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, client_message_id: clientMessageId, context }),
    });
  }
  cancel(turnId: string): Promise<{ status?: string }> {
    return this.json(`/turns/${encodeURIComponent(turnId)}/cancel`, { method: "POST", body: "{}" });
  }

  async streamEvents(turnId: string, after: number, signal: AbortSignal, onEvent: (event: ChatEvent) => void): Promise<number> {
    const response = await this.fetcher(`${this.baseUrl}/turns/${encodeURIComponent(turnId)}/events?after=${after}`, {
      headers: this.headers({ Accept: "text/event-stream" }), signal,
    });
    if (!response.ok) await parseResponse(response);
    if (!response.body) throw new ChatApiError("El navegador no pudo abrir el flujo de eventos.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let lastSeq = after;
    const dispatch = (frame: string) => {
      let eventName = "message";
      let id: number | undefined;
      const dataLines: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (!line || line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon < 0 ? line : line.slice(0, colon);
        const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "event") eventName = value;
        if (field === "id" && /^\d+$/.test(value)) id = Number(value);
        if (field === "data") dataLines.push(value);
      }
      if (!dataLines.length) return;
      let payload: Record<string, unknown>;
      try {
        const parsed: unknown = JSON.parse(dataLines.join("\n"));
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Expected event object");
        payload = parsed as Record<string, unknown>;
      }
      catch { throw new ChatApiError("El servidor envió un evento inválido."); }
      // The SSE frame's own id/event fields are authoritative; payload keys
      // with the same names are data and must not override them.
      const seq = id ?? (typeof payload.seq === "number" ? payload.seq : undefined);
      if (seq !== undefined && seq <= lastSeq) return;
      if (seq !== undefined) lastSeq = seq;
      const type = eventName !== "message" ? eventName : typeof payload.type === "string" ? payload.type : eventName;
      onEvent({ ...payload, ...(seq === undefined ? {} : { seq }), type } as ChatEvent);
    };
    while (true) {
      const { value, done } = await reader.read();
      // A replaced or closed listener must never render: stop even if the
      // underlying stream ignores the abort signal.
      if (signal.aborted) { await reader.cancel().catch(() => undefined); return lastSeq; }
      buffer += decoder.decode(value, { stream: !done });
      let boundary = buffer.search(/\r?\n\r?\n/);
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        const delimiter = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] ?? "\n\n";
        buffer = buffer.slice(boundary + delimiter.length);
        if (signal.aborted) return lastSeq;
        dispatch(frame);
        boundary = buffer.search(/\r?\n\r?\n/);
      }
      // Only an incomplete frame is bounded: a replay may deliver many small
      // complete frames in one network chunk.
      if (buffer.length > 128_000) throw new ChatApiError("El servidor envió un evento demasiado grande.");
      if (done) break;
    }
    return lastSeq;
  }
}
