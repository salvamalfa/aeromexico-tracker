import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccessClient, CHAT_API } from "./client";

const expires = "2026-10-04T12:00:00Z";
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("AccessClient", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    history.replaceState(null, "", "/access.html");
  });

  it("verifies login in memory and only calls health, login, and logout", async () => {
    const token = "owner-session-secret";
    const fetcher = vi.fn< typeof fetch >()
      .mockResolvedValueOnce(json({ status: "degraded", auth: "password", admission: "closed" }))
      .mockResolvedValueOnce(json({ session: token, expires_at: expires }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new AccessClient(fetcher);

    expect((await client.health()).status).toBe("degraded");
    expect(await client.login("owner-password-secret")).toBe(expires);
    await client.logout();

    const [health, login, logout] = fetcher.mock.calls;
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      `${CHAT_API}/health`, `${CHAT_API}/login`, `${CHAT_API}/logout`,
    ]);
    for (const [, options] of fetcher.mock.calls) {
      expect(options?.mode).toBe("cors");
      expect(options?.credentials).toBe("omit");
    }
    expect(health?.[1]?.method).toBe("GET");
    expect(JSON.parse(String(login?.[1]?.body))).toEqual({ password: "owner-password-secret" });
    expect(logout?.[1]?.method).toBe("POST");
    expect(new Headers(logout?.[1]?.headers).get("Authorization")).toBe(`Bearer ${token}`);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(location.href).not.toContain(token);
    expect(location.href).not.toContain("owner-password-secret");
  });

  it("does not retain a token when login fails or returns invalid JSON", async () => {
    const unauthorized = new AccessClient(vi.fn<typeof fetch>().mockResolvedValue(json({ detail: "invalid password" }, 401)));
    await expect(unauthorized.login("wrong")).rejects.toMatchObject({ status: 401 });
    await expect(unauthorized.logout()).resolves.toBeUndefined();

    const malformed = new AccessClient(vi.fn<typeof fetch>().mockResolvedValue(new Response("not-json", { status: 200 })));
    await expect(malformed.login("secret")).rejects.toThrow("no se pudo leer");
    await expect(malformed.logout()).resolves.toBeUndefined();
  });

  it("blocks repeat and concurrent logins while preserving the active token until logout", async () => {
    let resolveLogin!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { resolveLogin = resolve; });
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json({ session: "original-token", expires_at: expires }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockImplementationOnce(() => pending);
    const client = new AccessClient(fetcher);

    await client.login("first-password");
    await expect(client.login("second-password")).rejects.toThrow("Cierra la sesión");
    expect(fetcher).toHaveBeenCalledTimes(1);

    await client.logout();
    expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).get("Authorization")).toBe("Bearer original-token");
    expect(client.hasActiveSession).toBe(false);

    const login = client.login("after-logout-password");
    await expect(client.login("concurrent-password")).rejects.toThrow("Cierra la sesión");
    expect(fetcher).toHaveBeenCalledTimes(3);
    resolveLogin(json({ session: "new-token", expires_at: expires }));
    await expect(login).resolves.toBe(expires);
  });

  it("retains the session handle after failed logout and retries the same bearer", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json({ session: "temporary-token", expires_at: expires }))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new AccessClient(fetcher);
    await client.login("password");
    await expect(client.logout()).rejects.toThrow("sesión sigue activa");
    expect(client.hasActiveSession).toBe(true);
    await client.logout();
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).get("Authorization")).toBe("Bearer temporary-token");
    expect(new Headers(fetcher.mock.calls[2]?.[1]?.headers).get("Authorization")).toBe("Bearer temporary-token");
    expect(client.hasActiveSession).toBe(false);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("releases an already-invalid session on 401 but retains it on server errors", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json({ session: "expired-token", expires_at: expires }))
      .mockResolvedValueOnce(json({ detail: "invalid session" }, 401))
      .mockResolvedValueOnce(json({ session: "replacement-token", expires_at: expires }))
      .mockResolvedValueOnce(json({ detail: "unavailable" }, 503));
    const client = new AccessClient(fetcher);

    await client.login("first-password");
    await expect(client.logout()).rejects.toMatchObject({ status: 401 });
    expect(client.hasActiveSession).toBe(false);
    await client.login("second-password");
    await expect(client.logout()).rejects.toMatchObject({ status: 503 });
    expect(client.hasActiveSession).toBe(true);
    expect(new Headers(fetcher.mock.calls[3]?.[1]?.headers).get("Authorization")).toBe("Bearer replacement-token");
  });

  it("turns network and malformed health responses into safe errors", async () => {
    const offline = new AccessClient(vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));
    await expect(offline.health()).rejects.toThrow("No fue posible contactar");
    const malformed = new AccessClient(vi.fn<typeof fetch>().mockResolvedValue(json({ nope: true })));
    await expect(malformed.health()).rejects.toThrow("no se pudo leer");
  });
});
