import { apiRequest, clearAccessToken, hasAccessToken } from "./shared/api.js";
import {
  initializeShell,
  renderAnonymousIdentity,
  renderIdentity,
  setAdminNavigationVisible,
} from "./shared/shell.js";

const form = document.querySelector("#standalone-registration-form");
const button = document.querySelector("#standalone-registration-button");
const message = document.querySelector("#standalone-registration-message");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";
  button.disabled = true;
  const data = new FormData(form);
  const displayName = data.get("display_name").trim();
  try {
    await apiRequest("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: data.get("username"),
        password: data.get("password"),
        display_name: displayName || null,
        scope_name: data.get("scope_name"),
      }),
    });
    form.reset();
    form.querySelector('[name="scope_name"]').value = "default";
    message.textContent =
      "Anfrage eingereicht. Die Anmeldung ist nach der Freischaltung möglich.";
  } catch (_error) {
    message.textContent =
      "Bitte prüfe deine Angaben und verwende mindestens zwölf Passwortzeichen.";
  } finally {
    button.disabled = false;
  }
});

initializeShell();

if (hasAccessToken()) {
  Promise.all([
    apiRequest("/api/v1/auth/me"),
    apiRequest("/api/v1/scopes/manageable"),
  ])
    .then(([mePayload, manageablePayload]) => {
      renderIdentity(mePayload.principal);
      setAdminNavigationVisible(manageablePayload.scopes.length > 0);
    })
    .catch(() => {
      clearAccessToken();
      renderAnonymousIdentity();
    });
}
