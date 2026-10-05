import { AccessClient, AccessError } from "./client";

const client = new AccessClient();
const form = document.querySelector<HTMLFormElement>("#login-form");
const passwordField = document.querySelector<HTMLInputElement>("#password");
const loginButton = document.querySelector<HTMLButtonElement>("#login-button");
const accessStatus = document.querySelector<HTMLElement>("#access-status");
const logoutButton = document.querySelector<HTMLButtonElement>("#logout-button");
const healthButton = document.querySelector<HTMLButtonElement>("#health-button");
const healthStatus = document.querySelector<HTMLElement>("#health-status");

function show(node: HTMLElement | null, message: string, kind?: string): void {
  if (!node) return;
  node.textContent = message;
  if (kind) node.dataset.kind = kind;
  else delete node.dataset.kind;
}

function errorText(error: unknown): string {
  return error instanceof AccessError ? error.message : "No fue posible completar la solicitud.";
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!passwordField || !loginButton) return;
  loginButton.disabled = true;
  show(accessStatus, "Verificando…");
  try {
    const expiresAt = await client.login(passwordField.value);
    passwordField.value = "";
    show(accessStatus, `Contraseña correcta. Acceso verificado. Chat todavía pendiente de evaluación. La sesión vence: ${expiresAt}.`, "success");
    if (logoutButton) logoutButton.hidden = false;
  } catch (error) {
    passwordField.value = "";
    show(accessStatus, errorText(error), "error");
  } finally {
    loginButton.disabled = !client.canLogin;
  }
});

logoutButton?.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await client.logout();
    show(accessStatus, "Sesión cerrada.");
    if (logoutButton) logoutButton.hidden = true;
    if (loginButton) loginButton.disabled = false;
  } catch (error) {
    show(accessStatus, errorText(error), "error");
    if (!client.hasActiveSession) {
      if (logoutButton) logoutButton.hidden = true;
      if (loginButton) loginButton.disabled = false;
    }
  } finally {
    logoutButton.disabled = false;
  }
});

healthButton?.addEventListener("click", async () => {
  healthButton.disabled = true;
  show(healthStatus, "Consultando…");
  try {
    const result = await client.health();
    show(healthStatus, `Estado: ${result.status}${result.auth ? ` · acceso ${result.auth}` : ""}${result.admission ? ` · admisión ${result.admission}` : ""}.`);
  } catch (error) {
    show(healthStatus, errorText(error));
  } finally {
    healthButton.disabled = false;
  }
});
