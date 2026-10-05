export const CHAT_API = "https://aeromexico-tracker-production.up.railway.app/api/chat";

export interface HealthStatus {
  status: string;
  auth?: string;
  admission?: string;
}

interface LoginPayload {
  session: string;
  expires_at: string;
}

export class AccessError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "AccessError";
  }
}

type Fetcher = typeof fetch;

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new AccessError("La respuesta del servicio no se pudo leer.", response.status);
  }
}

function detailOf(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.length < 180) return detail;
  }
  return fallback;
}

export class AccessClient {
  private token: string | null = null;
  private loginInFlight = false;
  private logoutInFlight: Promise<void> | null = null;

  constructor(private readonly fetcher: Fetcher = fetch) {}

  get hasActiveSession(): boolean {
    return this.token !== null;
  }

  get canLogin(): boolean {
    return this.token === null && !this.loginInFlight;
  }

  async health(): Promise<HealthStatus> {
    let response: Response;
    try {
      response = await this.fetcher(`${CHAT_API}/health`, {
        method: "GET", mode: "cors", credentials: "omit", headers: { Accept: "application/json" },
      });
    } catch {
      throw new AccessError("No fue posible contactar el servicio.");
    }
    const payload = await readJson(response);
    if (!response.ok) throw new AccessError(detailOf(payload, "El servicio no está disponible."), response.status);
    if (!payload || typeof payload !== "object" || typeof (payload as HealthStatus).status !== "string") {
      throw new AccessError("La respuesta del servicio no se pudo leer.", response.status);
    }
    return payload as HealthStatus;
  }

  async login(password: string): Promise<string> {
    if (this.token || this.loginInFlight) {
      throw new AccessError("Cierra la sesión actual antes de iniciar otra.");
    }
    this.loginInFlight = true;
    let response: Response;
    try {
      try {
        response = await this.fetcher(`${CHAT_API}/login`, {
          method: "POST", mode: "cors", credentials: "omit",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        });
      } catch {
        throw new AccessError("No fue posible contactar el servicio.");
      }
      const payload = await readJson(response);
      if (!response.ok) throw new AccessError(detailOf(payload, "No se pudo verificar el acceso."), response.status);
      if (!payload || typeof payload !== "object") throw new AccessError("La respuesta de acceso no es válida.");
      const result = payload as Partial<LoginPayload>;
      if (typeof result.session !== "string" || !result.session || typeof result.expires_at !== "string") {
        throw new AccessError("La respuesta de acceso no es válida.");
      }
      this.token = result.session;
      return result.expires_at;
    } finally {
      this.loginInFlight = false;
    }
  }

  logout(): Promise<void> {
    if (this.logoutInFlight) return this.logoutInFlight;
    const token = this.token;
    if (!token) return Promise.resolve();
    const request = (async () => {
      try {
        const response = await this.fetcher(`${CHAT_API}/logout`, {
          method: "POST", mode: "cors", credentials: "omit",
          headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
        });
        if (response.status === 401) {
          this.token = null;
          throw new AccessError("La sesión ya no está activa en el servicio.", response.status);
        }
        if (!response.ok) throw new AccessError("La sesión local sigue activa porque el servicio no confirmó el cierre.", response.status);
        this.token = null;
      } catch (error) {
        if (error instanceof AccessError) throw error;
        throw new AccessError("La sesión sigue activa porque no fue posible confirmar el cierre en el servicio.");
      }
    })();
    this.logoutInFlight = request;
    void request.finally(() => {
      if (this.logoutInFlight === request) this.logoutInFlight = null;
    }).catch(() => undefined);
    return request;
  }
}
