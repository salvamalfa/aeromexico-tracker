import { afterEach, describe, expect, it, vi } from "vitest";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("access page bootstrap", () => {
  it("keeps login closed after success, offers logout retry, then returns to login", async () => {
    document.body.innerHTML = `
      <form id="login-form"><input id="password"><button id="login-button"></button></form>
      <p id="access-status"></p><button id="logout-button" hidden></button>
      <button id="health-button"></button><p id="health-status"></p>
    `;
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(json({ session: "active-session", expires_at: "later" }))
      .mockResolvedValueOnce(json({ detail: "temporarily unavailable" }, 503))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    await import("./bootstrap");

    const form = document.querySelector<HTMLFormElement>("#login-form")!;
    const password = document.querySelector<HTMLInputElement>("#password")!;
    const loginButton = document.querySelector<HTMLButtonElement>("#login-button")!;
    const logoutButton = document.querySelector<HTMLButtonElement>("#logout-button")!;
    password.value = "password";
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(logoutButton.hidden).toBe(false));
    expect(password.value).toBe("");
    expect(loginButton.disabled).toBe(true);

    logoutButton.click();
    await vi.waitFor(() => expect(logoutButton.disabled).toBe(false));
    expect(logoutButton.hidden).toBe(false);
    expect(loginButton.disabled).toBe(true);
    expect(document.querySelector("#access-status")?.textContent).toContain("sesión local sigue activa");

    logoutButton.click();
    await vi.waitFor(() => expect(logoutButton.hidden).toBe(true));
    expect(loginButton.disabled).toBe(false);
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(new Headers(fetcher.mock.calls[1]?.[1]?.headers).get("Authorization")).toBe("Bearer active-session");
    expect(new Headers(fetcher.mock.calls[2]?.[1]?.headers).get("Authorization")).toBe("Bearer active-session");
  });
});
