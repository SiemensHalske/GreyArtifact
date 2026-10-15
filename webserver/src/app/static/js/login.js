import {
  apiRequest,
  clearAccessToken,
  hasAccessToken,
  setAccessToken,
} from "./shared/api.js";
import { initializeShell } from "./shared/shell.js";

const form = document.querySelector("#standalone-login-form");
const button = document.querySelector("#standalone-login-button");
const message = document.querySelector("#standalone-login-message");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  button.disabled = true;
  const data = new FormData(form);
  try {
    const payload = await apiRequest("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: data.get("username"),
        password: data.get("password"),
      }),
    });
    setAccessToken(payload.access_token);
    window.location.assign("/");
  } catch (error) {
    clearAccessToken();
    message.textContent =
      error.status === 401
        ? "Benutzername oder Passwort ist nicht korrekt."
        : error.status === 429
          ? "Zu viele fehlgeschlagene Anmeldungen. Bitte später erneut versuchen."
          : "Anmeldung derzeit nicht möglich.";
  } finally {
    button.disabled = false;
  }
});

initializeShell();

if (hasAccessToken()) {
  apiRequest("/api/v1/auth/me")
    .then(() => window.location.assign("/"))
    .catch(() => clearAccessToken());
}
