import {
  apiRequest,
  clearAccessToken,
  hasAccessToken,
  setAccessToken,
} from "./shared/api.js";
import {
  initializeShell,
  renderAnonymousIdentity,
  renderIdentity,
} from "./shared/shell.js";
import { initializeProjectWorkspace } from "./dashboard/project_workspace.js";

const state = {
  activeScopeId: null,
  scopes: [],
};

const elements = {
  accessState: document.querySelector("#access-state"),
  apiState: document.querySelector("#api-state"),
  authModeToggle: document.querySelector("#auth-mode-toggle"),
  authPanel: document.querySelector("#auth-panel"),
  healthBadge: document.querySelector("#health-badge"),
  healthLabel: document.querySelector("#health-label"),
  loginButton: document.querySelector("#login-button"),
  loginForm: document.querySelector("#login-form"),
  loginMessage: document.querySelector("#login-message"),
  logoutButton: document.querySelector("#logout-button"),
  projectCount: document.querySelector("#project-count"),
  projectList: document.querySelector("#project-list"),
  registrationButton: document.querySelector("#registration-button"),
  registrationForm: document.querySelector("#registration-form"),
  registrationMessage: document.querySelector("#registration-message"),
  scopeCount: document.querySelector("#scope-count"),
  scopeSelect: document.querySelector("#scope-select"),
  workspacePanel: document.querySelector("#workspace-panel"),
};

const renderEmptyProjects = (title, message) => {
  elements.projectList.replaceChildren();
  const container = document.createElement("div");
  const heading = document.createElement("strong");
  const copy = document.createElement("span");
  container.className = "empty-state";
  heading.textContent = title;
  copy.textContent = message;
  container.append(heading, copy);
  elements.projectList.append(container);
};

const setLoggedOut = () => {
  clearAccessToken();
  state.activeScopeId = null;
  state.scopes = [];
  elements.authPanel.classList.remove("is-hidden");
  elements.workspacePanel.classList.add("is-hidden");
  elements.logoutButton.classList.add("is-hidden");
  renderAnonymousIdentity();
  elements.scopeCount.textContent = "—";
  elements.projectCount.textContent = "—";
  elements.accessState.textContent = "Gesperrt";
  elements.loginForm.reset();
};

const renderProjects = (projects) => {
  elements.projectList.replaceChildren();
  elements.projectCount.textContent = String(projects.length);
  if (projects.length === 0) {
    renderEmptyProjects(
      "Noch keine Projekte",
      "In diesem Arbeitsbereich sind keine Projekte sichtbar.",
    );
    return;
  }

  projects.forEach((project) => {
    const card = document.createElement("article");
    const header = document.createElement("div");
    const title = document.createElement("h3");
    const slug = document.createElement("code");
    const description = document.createElement("p");
    const openButton = document.createElement("button");
    card.className = "project-card";
    header.className = "project-card-header";
    title.textContent = project.name;
    slug.textContent = project.slug;
    description.textContent = project.description || "Keine Beschreibung hinterlegt.";
    openButton.className = "button button-quiet project-open";
    openButton.type = "button";
    openButton.textContent = "Öffnen →";
    openButton.addEventListener("click", () => projectWorkspace.open(project));
    header.append(title, slug);
    card.append(header, description, openButton);
    elements.projectList.append(card);
  });
};

const projectWorkspace = initializeProjectWorkspace({
  getScopeId: () => state.activeScopeId,
  refreshProjects: () => loadProjects(state.activeScopeId),
});

const loadProjects = async (scopeId) => {
  elements.projectCount.textContent = "…";
  renderEmptyProjects("Projekte werden geladen", "Autorisierte Daten werden abgefragt.");
  try {
    const payload = await apiRequest(`/api/v1/scopes/${scopeId}/projects`);
    if (state.activeScopeId === scopeId) {
      renderProjects(payload.projects);
    }
  } catch (error) {
    if (error.status === 401) {
      setLoggedOut();
      elements.loginMessage.textContent = "Deine Sitzung ist abgelaufen.";
      return;
    }
    elements.projectCount.textContent = "—";
    renderEmptyProjects("Nicht verfügbar", "Die Projekte konnten nicht geladen werden.");
  }
};

const renderScopes = () => {
  elements.scopeSelect.replaceChildren();
  elements.scopeCount.textContent = String(state.scopes.length);
  if (state.scopes.length === 0) {
    const option = document.createElement("option");
    option.textContent = "Keine sichtbaren Scopes";
    option.disabled = true;
    option.selected = true;
    elements.scopeSelect.append(option);
    elements.projectCount.textContent = "0";
    renderEmptyProjects(
      "Keine Arbeitsbereiche",
      "Für diese Identität ist noch keine lesbare Mitgliedschaft vorhanden.",
    );
    return;
  }

  state.scopes.forEach((scope) => {
    const option = document.createElement("option");
    option.value = scope.scope_id;
    option.textContent = scope.name;
    elements.scopeSelect.append(option);
  });
  state.activeScopeId = state.scopes[0].scope_id;
  loadProjects(state.activeScopeId);
};

const loadSession = async () => {
  const [mePayload, scopesPayload] = await Promise.all([
    apiRequest("/api/v1/auth/me"),
    apiRequest("/api/v1/scopes"),
  ]);
  state.scopes = scopesPayload.scopes;
  renderIdentity(mePayload.principal);
  elements.accessState.textContent = "Aktiv";
  elements.authPanel.classList.add("is-hidden");
  elements.workspacePanel.classList.remove("is-hidden");
  elements.logoutButton.classList.remove("is-hidden");
  renderScopes();
};

const handleLogin = async (event) => {
  event.preventDefault();
  elements.loginMessage.textContent = "";
  elements.loginButton.disabled = true;
  const formData = new FormData(elements.loginForm);
  try {
    const payload = await apiRequest("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
      }),
    });
    setAccessToken(payload.access_token);
    await loadSession();
  } catch (error) {
    clearAccessToken();
    elements.loginMessage.textContent =
      error.status === 401
        ? "Benutzername oder Passwort ist nicht korrekt."
        : "Anmeldung derzeit nicht möglich.";
  } finally {
    elements.loginButton.disabled = false;
  }
};

const handleRegistration = async (event) => {
  event.preventDefault();
  elements.registrationMessage.textContent = "";
  elements.registrationButton.disabled = true;
  const formData = new FormData(elements.registrationForm);
  const displayName = formData.get("display_name").trim();
  try {
    await apiRequest("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
        display_name: displayName || null,
        scope_name: formData.get("scope_name"),
      }),
    });
    elements.registrationForm.reset();
    elements.registrationForm.querySelector('[name="scope_name"]').value = "default";
    elements.registrationMessage.textContent =
      "Anfrage eingereicht. Die Anmeldung funktioniert nach der Freischaltung.";
  } catch (_error) {
    elements.registrationMessage.textContent =
      "Bitte prüfe die Angaben und verwende mindestens 12 Passwortzeichen.";
  } finally {
    elements.registrationButton.disabled = false;
  }
};

const toggleAuthMode = () => {
  const showRegistration = elements.registrationForm.classList.contains("is-hidden");
  elements.registrationForm.classList.toggle("is-hidden", !showRegistration);
  elements.loginForm.classList.toggle("is-hidden", showRegistration);
  elements.authModeToggle.setAttribute("aria-expanded", String(showRegistration));
  elements.authModeToggle.textContent = showRegistration
    ? "Schon freigeschaltet? Zur Anmeldung"
    : "Noch kein Konto? Registrierung anfragen";
};

const checkHealth = async () => {
  try {
    await apiRequest("/health");
    elements.healthBadge.dataset.state = "online";
    elements.healthLabel.textContent = "API erreichbar";
    elements.apiState.textContent = "Online";
  } catch (_error) {
    elements.healthBadge.dataset.state = "offline";
    elements.healthLabel.textContent = "API nicht erreichbar";
    elements.apiState.textContent = "Offline";
  }
};

initializeShell();
elements.loginForm.addEventListener("submit", handleLogin);
elements.registrationForm.addEventListener("submit", handleRegistration);
elements.authModeToggle.addEventListener("click", toggleAuthMode);
elements.logoutButton.addEventListener("click", setLoggedOut);
elements.scopeSelect.addEventListener("change", (event) => {
  state.activeScopeId = event.target.value;
  loadProjects(state.activeScopeId);
});
checkHealth();

if (hasAccessToken()) {
  loadSession().catch(() => {
    setLoggedOut();
    elements.loginMessage.textContent = "Bitte melde dich erneut an.";
  });
}
