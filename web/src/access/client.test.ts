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

  it("clears memory before a failed logout and never retries using a retained token", async () => {
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json({ session: "temporary-token", expires_at: expires }))
      .mockRejectedValueOnce(new TypeError("offline"));
    const client = new AccessClient(fetcher);
    await client.login("password");
    await expect(client.logout()).rejects.toThrow("sesión local se cerró");
    await expect(client.logout()).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("turns network and malformed health responses into safe errors", async () => {
    const offline = new AccessClient(vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));
    await expect(offline.health()).rejects.toThrow("No fue posible contactar");
    const malformed = new AccessClient(vi.fn<typeof fetch>().mockResolvedValue(json({ nope: true })));
    await expect(malformed.health()).rejects.toThrow("no se pudo leer");
  });
});
