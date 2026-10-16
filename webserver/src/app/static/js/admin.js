import {
  apiRequest,
  clearAccessToken,
  hasAccessToken,
  setAccessToken,
} from "./shared/api.js";
import {
  initializeShell,
  initials,
  renderAnonymousIdentity,
  renderIdentity,
  setAdminNavigationVisible,
} from "./shared/shell.js";

const BASE_ROLES = [
  ["viewer", "Viewer"],
  ["researcher", "Rechercheur"],
  ["analyst", "Analyst"],
  ["owner", "Owner"],
];

const ROLE_LABELS = Object.fromEntries([
  ...BASE_ROLES,
  ["pipeline_operator", "Pipeline Operator"],
]);

const EVENT_LABELS = {
  bootstrap: "Bootstrap",
  member_created: "Konto erstellt",
  migration_baseline: "System-Baseline",
  registration_approved: "Registrierung freigegeben",
  roles_updated: "Rollen geändert",
};

const state = {
  activeScopeId: null,
  auditPage: 1,
  auditPages: 0,
  scopes: [],
};

const elements = {
  activeScopeName: document.querySelector("#active-scope-name"),
  adminApp: document.querySelector("#admin-app"),
  adminDeniedPanel: document.querySelector("#admin-denied-panel"),
  adminLoginButton: document.querySelector("#admin-login-button"),
  adminLoginForm: document.querySelector("#admin-login-form"),
  adminLoginMessage: document.querySelector("#admin-login-message"),
  adminLoginPanel: document.querySelector("#admin-login-panel"),
  auditList: document.querySelector("#audit-list"),
  auditLoadMore: document.querySelector("#audit-load-more"),
  managedScopeCount: document.querySelector("#managed-scope-count"),
  memberCount: document.querySelector("#member-count"),
  memberForm: document.querySelector("#member-form"),
  memberList: document.querySelector("#member-list"),
  memberMessage: document.querySelector("#member-message"),
  memberSubmit: document.querySelector("#member-submit"),
  memberTotal: document.querySelector("#member-total"),
  pendingCount: document.querySelector("#pending-count"),
  registrationList: document.querySelector("#registration-list"),
  scopeSelect: document.querySelector("#admin-scope-select"),
};

const emptyState = (title, message) => {
  const container = document.createElement("div");
  const heading = document.createElement("strong");
  const copy = document.createElement("span");
  container.className = "admin-empty-state";
  heading.textContent = title;
  copy.textContent = message;
  container.append(heading, copy);
  return container;
};

const createRoleSelect = (selectedRole) => {
  const select = document.createElement("select");
  BASE_ROLES.forEach(([code, label]) => {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = label;
    option.selected = code === selectedRole;
    select.append(option);
  });
  return select;
};

const hasOperatorRole = (member) =>
  member.additional_roles?.includes("pipeline_operator") || false;

const setLoggedOut = () => {
  clearAccessToken();
  state.activeScopeId = null;
  state.auditPage = 1;
  state.auditPages = 0;
  state.scopes = [];
  renderAnonymousIdentity();
  elements.adminApp.classList.add("is-hidden");
  elements.adminDeniedPanel.classList.add("is-hidden");
  elements.adminLoginPanel.classList.remove("is-hidden");
  elements.adminLoginForm.reset();
  elements.pendingCount.textContent = "—";
  elements.memberCount.textContent = "—";
  elements.managedScopeCount.textContent = "—";
};

const createRoleBadges = (member) => {
  const badges = document.createElement("div");
  const baseRole = document.createElement("span");
  badges.className = "member-role-badges";
  baseRole.className = "role-badge";
  baseRole.textContent = ROLE_LABELS[member.role] || member.role;
  badges.append(baseRole);
  if (hasOperatorRole(member)) {
    const operator = document.createElement("span");
    operator.className = "role-badge role-badge-operator";
    operator.textContent = ROLE_LABELS.pipeline_operator;
    badges.append(operator);
  }
  return badges;
};

const renderMembers = (members) => {
  elements.memberList.replaceChildren();
  elements.memberCount.textContent = String(members.length);
  elements.memberTotal.textContent = `${members.length} ${members.length === 1 ? "Person" : "Personen"}`;

  if (members.length === 0) {
    elements.memberList.append(
      emptyState("Keine Mitglieder", "Dieser Arbeitsbereich hat noch keine Mitgliedschaften."),
    );
    return;
  }

  members.forEach((member) => {
    const row = document.createElement("article");
    const summary = document.createElement("div");
    const avatar = document.createElement("span");
    const identity = document.createElement("div");
    const name = document.createElement("strong");
    const username = document.createElement("small");
    const status = document.createElement("span");
    const edit = document.createElement("button");
    const editor = document.createElement("div");
    const baseRoleLabel = document.createElement("label");
    const baseRoleCaption = document.createElement("span");
    const baseRole = createRoleSelect(member.role);
    const operatorLabel = document.createElement("label");
    const operator = document.createElement("input");
    const operatorText = document.createElement("span");
    const editorActions = document.createElement("div");
    const save = document.createElement("button");
    const cancel = document.createElement("button");
    const message = document.createElement("p");
    const visibleName = member.display_name || member.username;

    row.className = "admin-member-row";
    row.dataset.principalId = member.principal_id;
    summary.className = "member-summary";
    avatar.className = "member-avatar";
    identity.className = "member-identity";
    status.className = `account-status${member.is_active ? " is-active" : ""}`;
    edit.type = "button";
    edit.className = "button member-edit-button";
    edit.dataset.action = "edit-roles";
    edit.textContent = "Rollen bearbeiten";
    editor.className = "member-role-editor is-hidden";
    baseRoleLabel.className = "member-role-field";
    baseRoleCaption.textContent = "Basisrolle";
    baseRole.name = "role";
    operatorLabel.className = "operator-control member-operator-control";
    operator.type = "checkbox";
    operator.name = "pipeline_operator";
    operator.checked = hasOperatorRole(member);
    operatorText.textContent = "Pipeline Operator";
    editorActions.className = "member-editor-actions";
    save.type = "button";
    save.className = "button button-primary";
    save.dataset.action = "save-roles";
    save.textContent = "Speichern";
    cancel.type = "button";
    cancel.className = "button member-cancel-button";
    cancel.dataset.action = "cancel-roles";
    cancel.textContent = "Abbrechen";
    message.className = "form-message member-role-message";
    message.setAttribute("role", "status");

    avatar.textContent = initials(visibleName);
    name.textContent = visibleName;
    username.textContent = `@${member.username}`;
    status.textContent = member.is_active ? "Aktiv" : "Gesperrt";
    identity.append(name, username);
    summary.append(
      avatar,
      identity,
      status,
      createRoleBadges(member),
      edit,
    );
    baseRoleLabel.append(baseRoleCaption, baseRole);
    operatorLabel.append(operator, operatorText);
    editorActions.append(save, cancel);
    editor.append(baseRoleLabel, operatorLabel, editorActions, message);
    row.append(summary, editor);
    elements.memberList.append(row);
  });
};

const formatTimestamp = (value) => {
  if (!value) {
    return "Zeitpunkt unbekannt";
  }
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
};

const roleListLabel = (roles) =>
  roles.length > 0
    ? roles.map((role) => ROLE_LABELS[role] || role).join(" + ")
    : "Keine Rolle";

const renderAudit = (payload, append = false) => {
  if (!append) {
    elements.auditList.replaceChildren();
  }
  state.auditPage = payload.pagination.page;
  state.auditPages = payload.pagination.pages;

  if (!append && payload.events.length === 0) {
    elements.auditList.append(
      emptyState("Keine Änderungen", "Für diesen Arbeitsbereich gibt es noch keine Rollenereignisse."),
    );
  }

  payload.events.forEach((event) => {
    const item = document.createElement("article");
    const heading = document.createElement("div");
    const title = document.createElement("strong");
    const meta = document.createElement("small");
    const change = document.createElement("p");
    const actorName = event.changed_by
      ? event.changed_by.display_name || event.changed_by.username
      : "System";
    const principalName = event.principal.display_name || event.principal.username;
    item.className = "audit-item";
    heading.className = "audit-heading";
    title.textContent = EVENT_LABELS[event.event_type] || event.event_type;
    meta.textContent = `${formatTimestamp(event.changed_at)} · ${actorName}`;
    change.textContent = `${principalName}: ${roleListLabel(event.roles_before)} → ${roleListLabel(event.roles_after)}`;
    heading.append(title, meta);
    item.append(heading, change);
    elements.auditList.append(item);
  });

  elements.auditLoadMore.classList.toggle(
    "is-hidden",
    state.auditPage >= state.auditPages,
  );
  elements.auditLoadMore.disabled = false;
};

const renderRegistrations = (registrations) => {
  elements.registrationList.replaceChildren();
  elements.pendingCount.textContent = String(registrations.length);
  if (registrations.length === 0) {
    elements.registrationList.append(
      emptyState("Queue ist leer", "Aktuell warten keine Konten auf deine Freigabe."),
    );
    return;
  }

  registrations.forEach((registration) => {
    const card = document.createElement("article");
    const identity = document.createElement("div");
    const avatar = document.createElement("span");
    const copy = document.createElement("div");
    const name = document.createElement("strong");
    const meta = document.createElement("small");
    const actions = document.createElement("div");
    const roleLabel = document.createElement("label");
    const roleCaption = document.createElement("span");
    const role = createRoleSelect("viewer");
    const operatorLabel = document.createElement("label");
    const operator = document.createElement("input");
    const operatorText = document.createElement("span");
    const approve = document.createElement("button");
    const reject = document.createElement("button");
    const visibleName = registration.display_name || registration.username;

    card.className = "approval-card";
    identity.className = "approval-identity";
    avatar.className = "approval-avatar";
    copy.className = "member-identity";
    actions.className = "approval-actions";
    roleLabel.className = "approval-role";
    roleCaption.textContent = "Basisrolle";
    role.setAttribute("aria-label", `Basisrolle für ${registration.username}`);
    operatorLabel.className = "operator-control approval-operator";
    operator.type = "checkbox";
    operator.className = "operator-checkbox";
    operatorText.textContent = "Pipeline Operator";
    approve.type = "button";
    approve.className = "button approval-button approval-button-primary";
    approve.textContent = "Freigeben";
    approve.dataset.action = "approve";
    approve.dataset.principalId = registration.principal_id;
    reject.type = "button";
    reject.className = "button approval-button approval-button-reject";
    reject.textContent = "Ablehnen";
    reject.dataset.action = "reject";
    reject.dataset.principalId = registration.principal_id;
    avatar.textContent = initials(visibleName);
    name.textContent = visibleName;
    meta.textContent = `@${registration.username} · ${formatTimestamp(registration.requested_at)}`;
    copy.append(name, meta);
    identity.append(avatar, copy);
    roleLabel.append(roleCaption, role);
    operatorLabel.append(operator, operatorText);
    actions.append(roleLabel, operatorLabel, approve, reject);
    card.append(identity, actions);
    elements.registrationList.append(card);
  });
};

const loadScope = async (scopeId) => {
  state.activeScopeId = scopeId;
  state.auditPage = 1;
  const activeScope = state.scopes.find((scope) => scope.scope_id === scopeId);
  elements.activeScopeName.textContent = activeScope?.name || "Unbekannter Arbeitsbereich";
  elements.pendingCount.textContent = "…";
  elements.memberCount.textContent = "…";
  elements.auditLoadMore.classList.add("is-hidden");

  try {
    const [membersPayload, registrationsPayload, auditPayload] = await Promise.all([
      apiRequest(`/api/v1/scopes/${scopeId}/members`),
      apiRequest(`/api/v1/scopes/${scopeId}/registrations`),
      apiRequest(`/api/v1/scopes/${scopeId}/role-audit?page=1&per_page=50`),
    ]);
    if (state.activeScopeId === scopeId) {
      renderMembers(membersPayload.members);
      renderRegistrations(registrationsPayload.registrations);
      renderAudit(auditPayload);
    }
  } catch (error) {
    if (error.status === 401) {
      setLoggedOut();
      elements.adminLoginMessage.textContent = "Deine Sitzung ist abgelaufen.";
      return;
    }
    elements.registrationList.replaceChildren(
      emptyState("Nicht verfügbar", "Die Verwaltungsdaten konnten nicht geladen werden."),
    );
    elements.memberList.replaceChildren();
    elements.auditList.replaceChildren();
    elements.pendingCount.textContent = "—";
    elements.memberCount.textContent = "—";
  }
};

const renderScopes = () => {
  elements.scopeSelect.replaceChildren();
  elements.managedScopeCount.textContent = String(state.scopes.length);
  if (state.scopes.length === 0) {
    const option = document.createElement("option");
    option.textContent = "Keine verwaltbaren Arbeitsbereiche";
    option.disabled = true;
    option.selected = true;
    elements.scopeSelect.append(option);
    elements.activeScopeName.textContent = "Keine Admin-Berechtigung";
    elements.pendingCount.textContent = "0";
    elements.memberCount.textContent = "0";
    elements.registrationList.replaceChildren(
      emptyState(
        "Kein Verwaltungszugriff",
        "Für dieses Konto ist membership.manage in keinem Arbeitsbereich hinterlegt.",
      ),
    );
    elements.memberList.replaceChildren();
    elements.auditList.replaceChildren();
    elements.memberForm.classList.add("is-disabled");
    elements.memberForm.querySelectorAll("input, select, button").forEach((field) => {
      field.disabled = true;
    });
    return;
  }

  elements.memberForm.classList.remove("is-disabled");
  elements.memberForm.querySelectorAll("input, select, button").forEach((field) => {
    field.disabled = false;
  });
  state.scopes.forEach((scope) => {
    const option = document.createElement("option");
    option.value = scope.scope_id;
    option.textContent = scope.name;
    elements.scopeSelect.append(option);
  });
  loadScope(state.scopes[0].scope_id);
};

const loadAdmin = async () => {
  const [mePayload, scopesPayload] = await Promise.all([
    apiRequest("/api/v1/auth/me"),
    apiRequest("/api/v1/scopes/manageable"),
  ]);
  renderIdentity(mePayload.principal);
  state.scopes = scopesPayload.scopes;
  setAdminNavigationVisible(state.scopes.length > 0);
  elements.adminLoginPanel.classList.add("is-hidden");
  if (state.scopes.length === 0) {
    elements.adminApp.classList.add("is-hidden");
    elements.adminDeniedPanel.classList.remove("is-hidden");
    return;
  }
  elements.adminDeniedPanel.classList.add("is-hidden");
  elements.adminApp.classList.remove("is-hidden");
  renderScopes();
};

const handleLogin = async (event) => {
  event.preventDefault();
  elements.adminLoginMessage.textContent = "";
  elements.adminLoginButton.disabled = true;
  const formData = new FormData(elements.adminLoginForm);
  try {
    const payload = await apiRequest("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
      }),
    });
    setAccessToken(payload.access_token);
    await loadAdmin();
  } catch (error) {
    clearAccessToken();
    elements.adminLoginMessage.textContent =
      error.status === 401
        ? "Benutzername oder Passwort ist nicht korrekt."
        : error.status === 429
          ? "Zu viele fehlgeschlagene Anmeldungen. Bitte später erneut versuchen."
          : "Admin-Bereich derzeit nicht verfügbar.";
  } finally {
    elements.adminLoginButton.disabled = false;
  }
};

const handleRegistrationDecision = async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !state.activeScopeId) {
    return;
  }
  const card = button.closest(".approval-card");
  const action = button.dataset.action;
  const options = {method: "POST"};
  if (action === "approve") {
    options.body = JSON.stringify({
      role: card.querySelector("select").value,
      additional_roles: card.querySelector(".operator-checkbox").checked
        ? ["pipeline_operator"]
        : [],
    });
  }
  card.querySelectorAll("button, select, input").forEach((control) => {
    control.disabled = true;
  });

  try {
    await apiRequest(
      `/api/v1/scopes/${state.activeScopeId}/registrations/`
        + `${button.dataset.principalId}/${action}`,
      options,
    );
    await loadScope(state.activeScopeId);
  } catch (error) {
    if (error.status === 401) {
      setLoggedOut();
      elements.adminLoginMessage.textContent = "Deine Sitzung ist abgelaufen.";
      return;
    }
    elements.memberMessage.textContent =
      "Die Registrierungsanfrage konnte nicht bearbeitet werden.";
    card.querySelectorAll("button, select, input").forEach((control) => {
      control.disabled = false;
    });
  }
};

const handleMemberCreation = async (event) => {
  event.preventDefault();
  if (!state.activeScopeId) {
    return;
  }
  elements.memberMessage.textContent = "";
  elements.memberSubmit.disabled = true;
  const formData = new FormData(elements.memberForm);
  const displayName = formData.get("display_name").trim();
  try {
    await apiRequest(`/api/v1/scopes/${state.activeScopeId}/members`, {
      method: "POST",
      body: JSON.stringify({
        username: formData.get("username"),
        password: formData.get("password"),
        display_name: displayName || null,
        role: formData.get("role"),
        additional_roles: formData.get("pipeline_operator")
          ? ["pipeline_operator"]
          : [],
      }),
    });
    elements.memberForm.reset();
    elements.memberMessage.textContent = "Konto wurde angelegt.";
    await loadScope(state.activeScopeId);
  } catch (error) {
    if (error.status === 401) {
      setLoggedOut();
      elements.adminLoginMessage.textContent = "Deine Sitzung ist abgelaufen.";
      return;
    }
    elements.memberMessage.textContent =
      error.status === 409
        ? "Das Konto konnte nicht angelegt werden."
        : "Bitte prüfe die Angaben und verwende mindestens 12 Passwortzeichen.";
  } finally {
    elements.memberSubmit.disabled = false;
  }
};

const handleMemberRoleAction = async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !state.activeScopeId) {
    return;
  }
  const row = button.closest(".admin-member-row");
  const editor = row.querySelector(".member-role-editor");
  const message = row.querySelector(".member-role-message");
  if (button.dataset.action === "edit-roles") {
    editor.classList.remove("is-hidden");
    button.classList.add("is-hidden");
    return;
  }
  if (button.dataset.action === "cancel-roles") {
    await loadScope(state.activeScopeId);
    return;
  }
  if (button.dataset.action !== "save-roles") {
    return;
  }

  message.textContent = "";
  editor.querySelectorAll("button, select, input").forEach((control) => {
    control.disabled = true;
  });
  try {
    await apiRequest(
      `/api/v1/scopes/${state.activeScopeId}/members/${row.dataset.principalId}/roles`,
      {
        method: "PUT",
        body: JSON.stringify({
          role: editor.querySelector('select[name="role"]').value,
          additional_roles: editor.querySelector('input[name="pipeline_operator"]').checked
            ? ["pipeline_operator"]
            : [],
        }),
      },
    );
    elements.memberMessage.textContent = "Rollen wurden aktualisiert.";
    await loadScope(state.activeScopeId);
  } catch (error) {
    if (error.status === 401) {
      setLoggedOut();
      elements.adminLoginMessage.textContent = "Deine Sitzung ist abgelaufen.";
      return;
    }
    message.textContent =
      error.status === 409
        ? "Der letzte Owner eines Arbeitsbereichs kann nicht herabgestuft werden."
        : "Die Rollen konnten nicht aktualisiert werden.";
    editor.querySelectorAll("button, select, input").forEach((control) => {
      control.disabled = false;
    });
  }
};

const handleAuditLoadMore = async () => {
  if (!state.activeScopeId || state.auditPage >= state.auditPages) {
    return;
  }
  elements.auditLoadMore.disabled = true;
  try {
    const payload = await apiRequest(
      `/api/v1/scopes/${state.activeScopeId}/role-audit?page=${state.auditPage + 1}&per_page=50`,
    );
    renderAudit(payload, true);
  } catch (_error) {
    elements.auditLoadMore.disabled = false;
  }
};

initializeShell();
elements.adminLoginForm.addEventListener("submit", handleLogin);
elements.registrationList.addEventListener("click", handleRegistrationDecision);
elements.memberForm.addEventListener("submit", handleMemberCreation);
elements.memberList.addEventListener("click", handleMemberRoleAction);
elements.auditLoadMore.addEventListener("click", handleAuditLoadMore);
elements.scopeSelect.addEventListener("change", (event) => {
  elements.memberMessage.textContent = "";
  loadScope(event.target.value);
});

if (hasAccessToken()) {
  loadAdmin().catch(() => {
    setLoggedOut();
    elements.adminLoginMessage.textContent = "Bitte melde dich erneut an.";
  });
}
