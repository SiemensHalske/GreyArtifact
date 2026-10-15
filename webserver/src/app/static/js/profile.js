import {
  apiRequest,
  clearAccessToken,
  hasAccessToken,
  setAccessToken,
} from "./shared/api.js";
import {
  initials,
  initializeShell,
  renderIdentity,
  setAdminNavigationVisible,
} from "./shared/shell.js";

const elements = {
  accessPanel: document.querySelector("#profile-access-panel"),
  accessTitle: document.querySelector("#profile-access-title"),
  accessMessage: document.querySelector("#profile-access-message"),
  app: document.querySelector("#profile-app"),
  avatar: document.querySelector("#profile-avatar"),
  visibleName: document.querySelector("#profile-visible-name"),
  username: document.querySelector("#profile-username"),
  profileForm: document.querySelector("#profile-form"),
  profileMessage: document.querySelector("#profile-message"),
  passwordForm: document.querySelector("#password-form"),
  passwordMessage: document.querySelector("#password-message"),
};

const showAccessRequired = (message) => {
  elements.app.classList.add("is-hidden");
  elements.accessPanel.classList.remove("is-hidden");
  elements.accessTitle.textContent = "Anmeldung erforderlich.";
  elements.accessMessage.textContent = message;
};

const renderProfile = (value) => {
  const visibleName = value.display_name || value.username;
  renderIdentity(value);
  elements.avatar.textContent = initials(visibleName);
  elements.visibleName.textContent = visibleName;
  elements.username.textContent = `@${value.username}`;
  elements.profileForm.elements.display_name.value = value.display_name || "";
};

const loadProfile = async () => {
  if (!hasAccessToken()) {
    showAccessRequired("Melde dich auf dem Dashboard an, um dein Profil zu öffnen.");
    return;
  }
  try {
    const [mePayload, manageablePayload] = await Promise.all([
      apiRequest("/api/v1/auth/me"),
      apiRequest("/api/v1/scopes/manageable"),
    ]);
    renderProfile(mePayload.principal);
    setAdminNavigationVisible(manageablePayload.scopes.length > 0);
    elements.accessPanel.classList.add("is-hidden");
    elements.app.classList.remove("is-hidden");
  } catch (_error) {
    clearAccessToken();
    showAccessRequired("Deine Sitzung ist abgelaufen. Melde dich bitte erneut an.");
  }
};

elements.profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.profileMessage.textContent = "";
  const data = new FormData(elements.profileForm);
  const displayName = data.get("display_name").trim();
  try {
    const payload = await apiRequest("/api/v1/auth/me", {
      method: "PATCH",
      body: JSON.stringify({display_name: displayName || null}),
    });
    renderProfile(payload.principal);
    elements.profileMessage.textContent = "Profil gespeichert.";
  } catch (error) {
    elements.profileMessage.textContent = error.message;
  }
});

elements.passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.passwordMessage.textContent = "";
  const data = new FormData(elements.passwordForm);
  if (data.get("new_password") !== data.get("confirm_password")) {
    elements.passwordMessage.textContent = "Die neuen Passwörter stimmen nicht überein.";
    return;
  }
  try {
    const changed = await apiRequest("/api/v1/auth/password", {
      method: "PUT",
      body: JSON.stringify({
        current_password: data.get("current_password"),
        new_password: data.get("new_password"),
      }),
    });
    setAccessToken(changed.access_token);
    elements.passwordForm.reset();
    elements.passwordMessage.textContent =
      "Passwort wurde geändert. Andere Sitzungen wurden abgemeldet.";
  } catch (error) {
    elements.passwordMessage.textContent =
      error.status === 400
        ? "Das aktuelle Passwort ist nicht korrekt."
        : error.message;
  }
});

initializeShell();
loadProfile();
