import {
  apiFetch,
  apiRequest,
  clearAccessToken,
  hasAccessToken,
} from "./shared/api.js";
import {
  initializeShell,
  renderIdentity,
  setAdminNavigationVisible,
} from "./shared/shell.js";

const byId = (id) => document.querySelector(`#${id}`);

const elements = {
  page: byId("project-page"),
  accessPanel: byId("project-access-panel"),
  accessTitle: byId("project-access-title"),
  accessMessage: byId("project-access-message"),
  app: byId("project-app"),
  pageMessage: byId("project-page-message"),
  title: byId("project-title"),
  description: byId("project-description"),
  overviewDescription: byId("project-overview-description"),
  breadcrumbName: byId("project-breadcrumb-name"),
  scopeName: byId("project-scope-name"),
  slug: byId("project-slug"),
  tabs: [...document.querySelectorAll("[data-project-view]")],
  panels: [...document.querySelectorAll("[data-project-panel]")],
  editForm: byId("project-edit-form"),
  editMessage: byId("project-edit-message"),
  importForm: byId("import-form"),
  importFormat: byId("import-format"),
  importFile: byId("import-file"),
  importText: byId("import-text"),
  importTextGroup: byId("import-text-group"),
  importFormatHint: byId("import-format-hint"),
  importMessage: byId("import-message"),
  importList: byId("import-list"),
  importsRefresh: byId("imports-refresh"),
  findingFilter: byId("finding-filter-form"),
  findingList: byId("finding-list"),
  findingDetail: byId("finding-detail"),
  mlBatchSelect: byId("ml-batch-select"),
  mlList: byId("ml-list"),
  mlDetail: byId("ml-detail"),
  mlClaimsSummary: byId("ml-claims-summary"),
  assetFilter: byId("asset-filter-form"),
  assetList: byId("asset-list"),
  evidence: byId("evidence-detail"),
  engagementForm: byId("engagement-form"),
  engagementMessage: byId("engagement-message"),
  engagementList: byId("engagement-list"),
  runList: byId("run-list"),
  runsRefresh: byId("runs-refresh"),
};

const state = {
  project: null,
  loadedViews: new Set(),
};

const projectId = elements.page.dataset.projectId;
const validViews = new Set(["overview", "findings", "ml", "evidence", "imports", "recon", "settings"]);
const importFormatLabels = {
  simple_list: "Einfache Asset-Liste",
  subfinder: "Subfinder JSONL",
  dnsx: "DNSx JSONL",
  httpx: "ProjectDiscovery HTTPx JSONL",
  nuclei: "ProjectDiscovery Nuclei JSONL",
};
const findingStatusLabels = {
  new: "Neu",
  confirmed: "Bestätigt",
  false_positive: "False Positive",
  remediated: "Behoben",
  accepted: "Akzeptiert",
};
const modelStatusLabels = {
  candidate: "Kandidat – nicht validiert",
  validated: "Validiert",
  approved: "Freigegeben",
  retired: "Ausgemustert",
};
const modelStatusSeverity = (status) =>
  status === "validated" || status === "approved" ? "low" : "medium";
const reviewDecisionLabels = {
  expected: "Erwartbar",
  data_artifact: "Datenartefakt",
  review_worthy: "Prüfenswert",
  confirmed_finding: "Bestätigter Befund",
};
const claimLabels = {
  "asset.belongs_to_engagement": "Gehört zum Engagement",
  "asset.publicly_reachable": "Öffentlich erreichbar",
  "exposure.internal_system": "Internes System",
  "exposure.admin_interface": "Admin-Oberfläche",
  "change.material_since_previous_snapshot": "Wesentlich verändert",
};
const claimStateLabels = {
  supported: "gestützt",
  contradicted: "widerlegt",
  unknown: "unbekannt",
  insufficient_evidence: "zu wenig Belege",
  abstain: "keine Aussage",
};
const evidenceDirectionLabels = {
  supports: "stützt",
  contradicts: "widerspricht",
  neutral: "neutral",
};
const acquisitionDecisionLabels = {
  approved: "freigegeben",
  rejected: "abgelehnt",
  revoked: "widerrufen",
};
const claimStateSeverity = (state) =>
  state === "supported" ? "medium" : state === "contradicted" ? "low" : "info";

const textElement = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
};

const empty = (container, message) => {
  container.replaceChildren(textElement("p", "record-empty", message));
};

const targetLines = (value) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((domain) => ({ domain, include_subdomains: true }));

const updateImportForm = () => {
  const simpleList = elements.importFormat.value === "simple_list";
  elements.importTextGroup.classList.toggle("is-hidden", !simpleList);
  elements.importFile.required = !simpleList;
  elements.importFile.accept = simpleList
    ? ".txt,text/plain"
    : ".jsonl,application/x-ndjson,application/json";
  elements.importFormatHint.textContent = simpleList
    ? "Für einfache Listen genügt eine Datei oder eingefügter Text."
    : "Für dieses Werkzeugformat ist eine JSONL-Datei erforderlich.";
  if (!simpleList) elements.importText.value = "";
};

const requireProject = () => {
  if (!state.project) throw new Error("Projekt ist nicht geladen.");
  return state.project;
};

const showAccessPanel = (title, message) => {
  elements.app.classList.add("is-hidden");
  elements.accessPanel.classList.remove("is-hidden");
  elements.accessTitle.textContent = title;
  elements.accessMessage.textContent = message;
};

const handleRequestError = (error) => {
  if (error.status === 401) {
    clearAccessToken();
    showAccessPanel(
      "Anmeldung erforderlich.",
      "Deine Sitzung ist abgelaufen. Melde dich auf dem Dashboard erneut an.",
    );
    return;
  }
  elements.pageMessage.textContent = error.message;
};

const loadImports = async () => {
  const project = requireProject();
  const payload = await apiRequest(`/api/v1/projects/${project.project_id}/imports`);
  elements.importList.replaceChildren();
  if (!payload.imports.length) {
    empty(elements.importList, "Noch keine Reports.");
    return;
  }

  payload.imports.forEach((item) => {
    const row = textElement("article", "record-row", "");
    const copy = document.createElement("div");
    copy.append(
      textElement("strong", "", item.original_filename),
      textElement(
        "small",
        "",
        `${importFormatLabels[item.parser_name] || item.parser_name} · ${item.status} · ${item.byte_size} Bytes`,
      ),
    );
    const actions = textElement("div", "record-actions", "");
    if (item.status !== "completed") {
      const process = textElement("button", "button button-quiet", "Verarbeiten");
      process.type = "button";
      process.addEventListener("click", async () => {
        process.disabled = true;
        elements.importMessage.textContent = "";
        try {
          await apiRequest(
            `/api/v1/projects/${project.project_id}/imports/${item.import_id}/process`,
            { method: "POST" },
          );
          await loadImports();
          state.loadedViews.delete("evidence");
          state.loadedViews.delete("findings");
        } catch (error) {
          elements.importMessage.textContent = error.message;
          await loadImports();
        }
      });
      actions.append(process);
    }

    const download = textElement(
      "button",
      "button button-quiet",
      item.requires_sensitive_access ? "Original (geschützt)" : "Original",
    );
    download.type = "button";
    download.addEventListener("click", async () => {
      const response = await apiFetch(
        `/api/v1/projects/${project.project_id}/imports/${item.import_id}/artifact`,
      );
      if (!response.ok) {
        elements.importMessage.textContent =
          response.status === 403
            ? "Dieses Original kann sensible Werte enthalten. Der Download erfordert die Berechtigung sensitive.read."
            : "Das Original konnte nicht geladen werden.";
        return;
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = item.original_filename;
      link.click();
      URL.revokeObjectURL(url);
    });
    actions.append(download);
    row.append(copy, actions);
    elements.importList.append(row);
  });
};

const historyEventText = (event) => {
  const actor = event.actor.display_name || event.actor.username;
  const time = new Date(event.occurred_at).toLocaleString("de-DE");
  if (event.kind === "status") {
    const before = findingStatusLabels[event.status_before] || event.status_before;
    const after = findingStatusLabels[event.status_after] || event.status_after;
    return [`${time} · ${actor}`, `Status: ${before} → ${after}`];
  }
  return [`${time} · ${actor}`, event.body];
};

const renderFindingHistory = (container, events) => {
  container.replaceChildren(textElement("strong", "", "Verlauf"));
  if (!events.length) {
    container.append(textElement("small", "", "Noch keine Statusänderungen oder Notizen."));
    return;
  }
  events.forEach((event) => {
    const [meta, text] = historyEventText(event);
    const item = textElement("div", "finding-history-item", "");
    item.dataset.kind = event.kind;
    item.append(textElement("small", "", meta), textElement("p", "", text));
    container.append(item);
  });
};

const showFinding = async (findingId) => {
  const project = requireProject();
  const payload = await apiRequest(
    `/api/v1/projects/${project.project_id}/findings/${findingId}`,
  );
  const finding = payload.finding;
  elements.findingDetail.classList.remove("empty-state");
  elements.findingDetail.replaceChildren(
    textElement("strong", "", finding.title),
    textElement(
      "small",
      "",
      `${finding.external_id} · ${findingStatusLabels[finding.status] || finding.status} · ${finding.source}`,
    ),
  );
  const severity = textElement("span", "finding-severity", finding.severity);
  severity.dataset.severity = finding.severity;
  elements.findingDetail.append(
    severity,
    textElement("span", "", finding.description || "Keine Beschreibung im Report."),
    textElement("span", "", `Treffer: ${finding.matched_at}`),
  );
  if (finding.asset) {
    elements.findingDetail.append(
      textElement(
        "small",
        "",
        `Asset: ${finding.asset.type} · ${finding.asset.canonical_value}`,
      ),
    );
  }
  if (finding.is_sensitive) {
    elements.findingDetail.append(
      textElement(
        "p",
        "finding-sensitive-note",
        "Potenziell sensibler Treffer. Extrahierte Werte werden nur im geschützten Originalartefakt vorgehalten.",
      ),
    );
  }
  if (Object.keys(finding.metadata).length) {
    elements.findingDetail.append(
      textElement("small", "", `Metadaten: ${JSON.stringify(finding.metadata)}`),
    );
  }
  elements.findingDetail.append(
    textElement(
      "small",
      "",
      `${finding.parser_name}@${finding.parser_version} · ${finding.evidence_locator} · sha256:${finding.artifact_sha256.slice(0, 12)}…`,
    ),
  );

  const statusForm = textElement("form", "filter-form finding-status-form", "");
  const statusSelect = document.createElement("select");
  statusSelect.name = "status";
  statusSelect.setAttribute("aria-label", "Status des Findings ändern");
  Object.entries(findingStatusLabels).forEach(([value, label]) => {
    const option = textElement("option", "", label);
    option.value = value;
    option.selected = value === finding.status;
    statusSelect.append(option);
  });
  const statusSubmit = textElement("button", "button button-quiet", "Status speichern");
  statusSubmit.type = "submit";
  const statusMessage = textElement("small", "", "");
  statusMessage.setAttribute("role", "status");
  statusForm.append(statusSelect, statusSubmit);
  statusForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    statusSubmit.disabled = true;
    statusMessage.textContent = "";
    try {
      await apiRequest(
        `/api/v1/projects/${project.project_id}/findings/${finding.finding_id}/status`,
        { method: "PUT", body: JSON.stringify({ status: statusSelect.value }) },
      );
      await loadFindings();
      await showFinding(finding.finding_id);
    } catch (error) {
      if (error.status === 401) {
        handleRequestError(error);
        return;
      }
      statusMessage.textContent =
        error.status === 404
          ? "Status konnte nicht geändert werden. Dafür ist die Berechtigung data.import nötig."
          : error.message;
      statusSubmit.disabled = false;
    }
  });
  elements.findingDetail.append(statusForm, statusMessage);

  const history = textElement("div", "finding-history", "");
  const noteForm = textElement("form", "finding-note-form", "");
  const noteInput = document.createElement("textarea");
  noteInput.name = "body";
  noteInput.maxLength = 4000;
  noteInput.required = true;
  noteInput.rows = 3;
  noteInput.placeholder = "Analystennotiz (keine Secrets oder Zugangsdaten eintragen)";
  noteInput.setAttribute("aria-label", "Analystennotiz");
  const noteSubmit = textElement("button", "button button-quiet", "Notiz hinzufügen");
  noteSubmit.type = "submit";
  const noteMessage = textElement("small", "", "");
  noteMessage.setAttribute("role", "status");
  noteForm.append(noteInput, noteSubmit, noteMessage);
  const historyUrl = `/api/v1/projects/${project.project_id}/findings/${finding.finding_id}`;
  noteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    noteSubmit.disabled = true;
    noteMessage.textContent = "";
    try {
      await apiRequest(`${historyUrl}/notes`, {
        method: "POST",
        body: JSON.stringify({ body: noteInput.value }),
      });
      noteInput.value = "";
      const payload = await apiRequest(`${historyUrl}/history`);
      renderFindingHistory(history, payload.events);
    } catch (error) {
      if (error.status === 401) {
        handleRequestError(error);
        return;
      }
      noteMessage.textContent =
        error.status === 404
          ? "Notiz konnte nicht gespeichert werden. Dafür ist die Berechtigung data.import nötig."
          : error.message;
    }
    noteSubmit.disabled = false;
  });
  elements.findingDetail.append(history, noteForm);
  const historyPayload = await apiRequest(`${historyUrl}/history`);
  renderFindingHistory(history, historyPayload.events);
};

const loadFindings = async () => {
  const project = requireProject();
  const data = new FormData(elements.findingFilter);
  const params = new URLSearchParams();
  for (const key of ["q", "severity", "status"]) {
    if (data.get(key)) params.set(key, data.get(key));
  }
  const payload = await apiRequest(
    `/api/v1/projects/${project.project_id}/findings?${params}`,
  );
  elements.findingList.replaceChildren();
  elements.findingDetail.classList.add("empty-state");
  elements.findingDetail.textContent =
    "Finding auswählen, um Herkunft und Metadaten zu sehen.";
  if (!payload.findings.length) {
    empty(elements.findingList, "Keine passenden Findings.");
    return;
  }
  payload.findings.forEach((finding) => {
    const button = textElement("button", "asset-row finding-row", "");
    button.type = "button";
    const header = textElement("span", "finding-row-header", "");
    const severity = textElement("span", "finding-severity", finding.severity);
    severity.dataset.severity = finding.severity;
    header.append(textElement("strong", "", finding.title), severity);
    button.append(
      header,
      textElement("small", "", `${finding.external_id} · ${finding.matched_at}`),
    );
    button.addEventListener("click", () => {
      showFinding(finding.finding_id).catch(handleRequestError);
    });
    elements.findingList.append(button);
  });
};

const showEvidence = async (assetId) => {
  const project = requireProject();
  const payload = await apiRequest(
    `/api/v1/projects/${project.project_id}/assets/${assetId}`,
  );
  elements.evidence.classList.remove("empty-state");
  elements.evidence.replaceChildren(
    textElement("strong", "", payload.asset.display_value),
    textElement("small", "", `${payload.asset.type} · ${payload.asset.canonical_value}`),
  );
  if (!payload.observations.length) {
    elements.evidence.append(textElement("p", "record-empty", "Keine Beobachtungen vorhanden."));
    return;
  }
  payload.observations.forEach((observation) => {
    const item = textElement("article", "evidence-item", "");
    const reconOrigin = observation.recon_run_id
      ? ` · Run ${observation.recon_run_id.slice(0, 8)} / ${observation.recon_operation}`
      : "";
    item.append(
      textElement("strong", "", observation.code),
      textElement(
        "span",
        "",
        typeof observation.value === "string"
          ? observation.value
          : JSON.stringify(observation.value),
      ),
      textElement(
        "small",
        "",
        `${observation.parser_name}@${observation.parser_version} · ${observation.evidence_locator} · sha256:${observation.artifact_sha256.slice(0, 12)}…${reconOrigin}`,
      ),
    );
    elements.evidence.append(item);
  });
};

const loadAssets = async () => {
  const project = requireProject();
  const data = new FormData(elements.assetFilter);
  const params = new URLSearchParams();
  if (data.get("q")) params.set("q", data.get("q"));
  if (data.get("type")) params.set("type", data.get("type"));
  const payload = await apiRequest(
    `/api/v1/projects/${project.project_id}/assets?${params}`,
  );
  elements.assetList.replaceChildren();
  if (!payload.assets.length) {
    empty(elements.assetList, "Keine passenden Assets.");
    return;
  }
  payload.assets.forEach((asset) => {
    const button = textElement("button", "asset-row", "");
    button.type = "button";
    button.append(
      textElement("strong", "", asset.display_value),
      textElement("small", "", asset.type),
    );
    button.addEventListener("click", () => {
      showEvidence(asset.asset_id).catch(handleRequestError);
    });
    elements.assetList.append(button);
  });
};

const loadEngagements = async () => {
  const project = requireProject();
  const payload = await apiRequest(`/api/v1/projects/${project.project_id}/engagements`);
  elements.engagementList.replaceChildren();
  if (!payload.engagements.length) {
    empty(elements.engagementList, "Noch kein Engagement.");
    return;
  }
  payload.engagements.forEach((item) => {
    const row = textElement("article", "record-row", "");
    const copy = document.createElement("div");
    copy.append(
      textElement("strong", "", item.name),
      textElement("small", "", `${item.valid_from} – ${item.valid_until} · ${item.allowed_targets.length} Ziele`),
    );
    const start = textElement("button", "button button-primary", "Run starten");
    start.type = "button";
    start.addEventListener("click", async () => {
      start.disabled = true;
      elements.engagementMessage.textContent = "";
      try {
        await apiRequest(`/api/v1/engagements/${item.engagement_id}/runs`, {
          method: "POST",
        });
        await loadRuns();
      } catch (error) {
        elements.engagementMessage.textContent = error.message;
      } finally {
        start.disabled = false;
      }
    });
    row.append(copy, start);
    elements.engagementList.append(row);
  });
};

const loadRuns = async () => {
  const project = requireProject();
  const payload = await apiRequest(`/api/v1/projects/${project.project_id}/runs`);
  elements.runList.replaceChildren();
  if (!payload.runs.length) {
    empty(elements.runList, "Noch keine Runs.");
    return;
  }
  payload.runs.forEach((run) => {
    const row = textElement("article", "record-row run-row", "");
    const copy = document.createElement("div");
    copy.append(
      textElement("strong", "", `${run.profile_code} · ${run.status}`),
      textElement(
        "small",
        "",
        run.steps.map((step) => `${step.operation_code}:${step.status}`).join(" · "),
      ),
    );
    row.append(copy);
    if (["pending", "running"].includes(run.status)) {
      const cancel = textElement("button", "button button-quiet", "Abbrechen");
      cancel.type = "button";
      cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try {
          await apiRequest(`/api/v1/runs/${run.run_id}/cancel`, { method: "POST" });
          await loadRuns();
        } catch (error) {
          handleRequestError(error);
        }
      });
      row.append(cancel);
    }
    elements.runList.append(row);
  });
};

const candidateText = (candidate) => {
  let text = `Vorschlag, nicht ausgeführt: ${candidate.action_type} (${candidate.policy_class})`;
  const recommendation = candidate.recommendation;
  if (recommendation) {
    text +=
      ` · Empfehlung: Nutzwert ${recommendation.utility_score.toFixed(3)},` +
      ` Informationsgewinn ${recommendation.expected_information_gain.toFixed(3)}`;
    const decision = recommendation.decision;
    if (decision) {
      const validUntil = decision.valid_until ? new Date(decision.valid_until) : null;
      const until = validUntil
        ? ` bis ${validUntil.toLocaleString("de-DE")}${validUntil < new Date() ? " (abgelaufen)" : ""}`
        : "";
      text += ` · Entscheidung in Fennec: ${acquisitionDecisionLabels[decision.decision] || decision.decision}${until}`;
    }
  }
  return text;
};

const renderClaims = (container, claims) => {
  container.replaceChildren(textElement("strong", "", "Claims (Stage 8)"));
  if (!claims.length) {
    container.append(textElement("small", "", "Für dieses Asset liegen keine Claims vor."));
    return;
  }
  claims.forEach((claim) => {
    const row = textElement("div", "ml-claim", "");
    const header = textElement("span", "finding-row-header", "");
    const badge = textElement("span", "finding-severity", claimStateLabels[claim.state] || claim.state);
    badge.dataset.severity = claimStateSeverity(claim.state);
    header.append(textElement("span", "", claimLabels[claim.claim] || claim.claim), badge);
    row.append(header);
    if (claim.evidence.length) {
      const reasons = claim.evidence.map(
        (item) =>
          `${evidenceDirectionLabels[item.direction] || item.direction}: ${item.reason}` +
          (item.count > 1 ? ` (${item.count})` : ""),
      );
      row.append(textElement("small", "", reasons.join(" · ")));
    }
    claim.candidates.forEach((candidate) => row.append(textElement("small", "", candidateText(candidate))));
    container.append(row);
  });
  if (claims.some((claim) => claim.candidates.length)) {
    container.append(
      textElement("small", "", "Ausführung nur über Engagement und kontrollierten Runner, nie aus dieser Ansicht."),
    );
  }
};

const loadClaims = async (prediction, container) => {
  const payload = await apiRequest(
    `/api/v1/projects/${requireProject().project_id}/import-batches/${prediction.batch_id}/claims` +
      `?asset_id=${encodeURIComponent(prediction.asset.asset_id)}`,
  );
  // The detail may already show another prediction.
  if (container.isConnected) renderClaims(container, payload.claims);
};

const renderClaimsSummary = (summary) => {
  const byClaim = new Map();
  summary.forEach(({ claim, state, count }) => {
    if (!byClaim.has(claim)) byClaim.set(claim, []);
    byClaim.get(claim).push(`${count} ${claimStateLabels[state] || state}`);
  });
  elements.mlClaimsSummary.replaceChildren();
  elements.mlClaimsSummary.hidden = byClaim.size === 0;
  if (!byClaim.size) return;
  elements.mlClaimsSummary.append(textElement("strong", "", "Claims (Stage 8) in diesem Lauf"));
  byClaim.forEach((parts, claim) => {
    elements.mlClaimsSummary.append(
      textElement("small", "", `${claimLabels[claim] || claim}: ${parts.join(" · ")}`),
    );
  });
};

const showPrediction = (prediction) => {
  elements.mlDetail.classList.remove("empty-state");
  elements.mlDetail.replaceChildren(
    textElement("strong", "", prediction.asset.canonical_value),
    textElement(
      "small",
      "",
      `${prediction.asset.type} · Rang ${prediction.rank} · Perzentil ${prediction.percentile.toFixed(1)}`,
    ),
  );
  const status = textElement(
    "span",
    "finding-severity",
    modelStatusLabels[prediction.model_status] || prediction.model_status,
  );
  status.dataset.severity = modelStatusSeverity(prediction.model_status);
  elements.mlDetail.append(status, textElement("small", "", `Modell: ${prediction.model_version}`));
  if (Object.keys(prediction.explanation).length) {
    elements.mlDetail.append(
      textElement("small", "", `Erklärung: ${JSON.stringify(prediction.explanation)}`),
    );
  }
  if (prediction.review) {
    const reviewer = prediction.review.reviewer.display_name || prediction.review.reviewer.username;
    const time = new Date(prediction.review.created_at).toLocaleString("de-DE");
    elements.mlDetail.append(
      textElement(
        "small",
        "",
        `Bewertung: ${reviewDecisionLabels[prediction.review.decision] || prediction.review.decision} · ${reviewer} · ${time}`,
      ),
    );
  }

  const reviewForm = textElement("form", "finding-status-form", "");
  const reviewSelect = document.createElement("select");
  reviewSelect.name = "decision";
  reviewSelect.setAttribute("aria-label", "Bewertung der Vorhersage");
  Object.entries(reviewDecisionLabels).forEach(([value, label]) => {
    const option = textElement("option", "", label);
    option.value = value;
    option.selected = prediction.review && prediction.review.decision === value;
    reviewSelect.append(option);
  });
  const reviewSubmit = textElement("button", "button button-quiet", "Bewertung speichern");
  reviewSubmit.type = "submit";
  const reviewMessage = textElement("small", "", "");
  reviewMessage.setAttribute("role", "status");
  reviewForm.append(reviewSelect, reviewSubmit);
  reviewForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    reviewSubmit.disabled = true;
    reviewMessage.textContent = "";
    try {
      const payload = await apiRequest(
        `/api/v1/projects/${requireProject().project_id}/ml-predictions/${prediction.prediction_id}/review`,
        { method: "POST", body: JSON.stringify({ decision: reviewSelect.value }) },
      );
      prediction.review = payload.review;
      showPrediction(prediction);
    } catch (error) {
      if (error.status === 401) {
        handleRequestError(error);
        return;
      }
      reviewMessage.textContent =
        error.status === 404
          ? "Bewertung nicht möglich. Dafür ist die Berechtigung data.import nötig."
          : error.message;
      reviewSubmit.disabled = false;
    }
  });
  elements.mlDetail.append(reviewForm, reviewMessage);

  const toAsset = textElement("button", "button button-quiet", "Asset & Evidenz öffnen");
  toAsset.type = "button";
  toAsset.addEventListener("click", async () => {
    window.location.hash = "evidence";
    await selectView("evidence");
    showEvidence(prediction.asset.asset_id).catch(handleRequestError);
  });
  elements.mlDetail.append(toAsset);

  const claimsSection = textElement("div", "ml-claims", "");
  claimsSection.append(textElement("small", "", "Claims werden geladen …"));
  elements.mlDetail.append(claimsSection);
  loadClaims(prediction, claimsSection).catch(handleRequestError);
};

const loadPredictions = async (batchId) => {
  const project = requireProject();
  elements.mlList.replaceChildren();
  elements.mlDetail.classList.add("empty-state");
  elements.mlDetail.textContent = "Vorhersage auswählen, um Modell und Erklärung zu sehen.";
  renderClaimsSummary([]);
  if (!batchId) return;
  const [payload, claims] = await Promise.all([
    apiRequest(`/api/v1/projects/${project.project_id}/import-batches/${batchId}/predictions`),
    apiRequest(`/api/v1/projects/${project.project_id}/import-batches/${batchId}/claims`),
  ]);
  renderClaimsSummary(claims.summary);
  if (!payload.predictions.length) {
    empty(elements.mlList, "Dieser Lauf enthält keine Vorhersagen.");
    return;
  }
  payload.predictions.forEach((prediction) => {
    const button = textElement("button", "asset-row finding-row", "");
    button.type = "button";
    const header = textElement("span", "finding-row-header", "");
    const badge = textElement("span", "finding-severity", `#${prediction.rank}`);
    badge.dataset.severity = modelStatusSeverity(prediction.model_status);
    header.append(textElement("strong", "", prediction.asset.canonical_value), badge);
    button.append(
      header,
      textElement("small", "", `${prediction.asset.type} · Perzentil ${prediction.percentile.toFixed(1)}`),
    );
    button.addEventListener("click", () => showPrediction(prediction));
    elements.mlList.append(button);
  });
};

const loadBatches = async () => {
  const project = requireProject();
  const payload = await apiRequest(`/api/v1/projects/${project.project_id}/import-batches`);
  elements.mlBatchSelect.replaceChildren();
  if (!payload.batches.length) {
    const option = textElement("option", "", "Keine Läufe");
    option.value = "";
    elements.mlBatchSelect.append(option);
    elements.mlBatchSelect.disabled = true;
    await loadPredictions("");
    empty(elements.mlList, "Noch keine recon_ml-Läufe importiert.");
    return;
  }
  elements.mlBatchSelect.disabled = false;
  payload.batches.forEach((batch) => {
    const date = new Date(batch.created_at).toLocaleDateString("de-DE");
    const option = textElement(
      "option",
      "",
      `${batch.ml_model}@${batch.ml_model_version} · ${batch.external_run_ref} · ${date}`,
    );
    option.value = batch.batch_id;
    elements.mlBatchSelect.append(option);
  });
  await loadPredictions(elements.mlBatchSelect.value);
};

const viewLoaders = {
  findings: loadFindings,
  ml: loadBatches,
  evidence: loadAssets,
  imports: loadImports,
  recon: () => Promise.all([loadEngagements(), loadRuns()]),
};

const selectView = async (requestedView) => {
  const view = validViews.has(requestedView) ? requestedView : "overview";
  elements.tabs.forEach((tab) => {
    const active = tab.dataset.projectView === view;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  elements.panels.forEach((panel) => {
    panel.classList.toggle("is-hidden", panel.dataset.projectPanel !== view);
  });
  elements.pageMessage.textContent = "";

  const loader = viewLoaders[view];
  if (loader && !state.loadedViews.has(view)) {
    try {
      await loader();
      state.loadedViews.add(view);
    } catch (error) {
      handleRequestError(error);
    }
  }
};

const renderProject = (project, scopeName) => {
  const description = project.description || "Keine Beschreibung hinterlegt.";
  state.project = project;
  elements.title.textContent = project.name;
  elements.description.textContent = description;
  elements.overviewDescription.textContent = description;
  elements.breadcrumbName.textContent = project.name;
  elements.scopeName.textContent = scopeName;
  elements.slug.textContent = project.slug;
  elements.editForm.elements.slug.value = project.slug;
  elements.editForm.elements.name.value = project.name;
  elements.editForm.elements.description.value = project.description || "";
  document.title = `${project.name} · GreyArtifact`;
};

const loadSession = async () => {
  if (!hasAccessToken()) {
    showAccessPanel(
      "Anmeldung erforderlich.",
      "Melde dich auf dem Dashboard an, um diesen Projektbereich zu öffnen.",
    );
    return;
  }

  try {
    const [mePayload, projectPayload, scopesPayload, manageablePayload] = await Promise.all([
      apiRequest("/api/v1/auth/me"),
      apiRequest(`/api/v1/projects/${encodeURIComponent(projectId)}`),
      apiRequest("/api/v1/scopes"),
      apiRequest("/api/v1/scopes/manageable"),
    ]);
    const scope = scopesPayload.scopes.find(
      (item) => item.scope_id === projectPayload.project.scope_id,
    );
    renderIdentity(mePayload.principal);
    setAdminNavigationVisible(manageablePayload.scopes.length > 0);
    renderProject(projectPayload.project, scope?.name || "Arbeitsbereich");
    elements.accessPanel.classList.add("is-hidden");
    elements.app.classList.remove("is-hidden");
    await selectView(window.location.hash.slice(1));
  } catch (error) {
    if (error.status === 401) {
      clearAccessToken();
      showAccessPanel(
        "Anmeldung erforderlich.",
        "Deine Sitzung ist abgelaufen. Melde dich auf dem Dashboard erneut an.",
      );
      return;
    }
    showAccessPanel(
      "Projekt nicht verfügbar.",
      "Das Projekt existiert nicht oder ist für dein Konto nicht sichtbar.",
    );
  }
};

elements.tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const view = tab.dataset.projectView;
    if (window.location.hash === `#${view}`) {
      selectView(view);
    } else {
      window.location.hash = view;
    }
  });
});

window.addEventListener("hashchange", () => {
  selectView(window.location.hash.slice(1));
});

elements.editForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const project = requireProject();
  const data = new FormData(elements.editForm);
  elements.editMessage.textContent = "";
  try {
    const payload = await apiRequest(`/api/v1/projects/${project.project_id}`, {
      method: "PUT",
      body: JSON.stringify({
        slug: data.get("slug"),
        name: data.get("name"),
        description: data.get("description") || null,
      }),
    });
    renderProject(payload.project, elements.scopeName.textContent);
    elements.editMessage.textContent = "Gespeichert.";
  } catch (error) {
    elements.editMessage.textContent = error.message;
  }
});

elements.importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const project = requireProject();
  elements.importMessage.textContent = "";
  const simpleList = elements.importFormat.value === "simple_list";
  const hasFile = elements.importFile.files.length > 0;
  const hasText = Boolean(elements.importText.value.trim());
  if ((simpleList && hasFile === hasText) || (!simpleList && !hasFile)) {
    elements.importMessage.textContent = simpleList
      ? "Wähle entweder eine Datei oder eingefügten Text."
      : "Wähle eine JSONL-Datei aus.";
    return;
  }
  try {
    await apiRequest(`/api/v1/projects/${project.project_id}/imports`, {
      method: "POST",
      body: new FormData(elements.importForm),
    });
    elements.importForm.reset();
    updateImportForm();
    elements.importMessage.textContent =
      "Rohartefakt gespeichert; Verarbeitung startet nur auf Klick.";
    await loadImports();
  } catch (error) {
    elements.importMessage.textContent = error.message;
  }
});

elements.importsRefresh.addEventListener("click", () => {
  loadImports().catch(handleRequestError);
});

elements.importFormat.addEventListener("change", updateImportForm);

elements.assetFilter.addEventListener("submit", (event) => {
  event.preventDefault();
  loadAssets().catch(handleRequestError);
});

elements.mlBatchSelect.addEventListener("change", () => {
  loadPredictions(elements.mlBatchSelect.value).catch(handleRequestError);
});

elements.findingFilter.addEventListener("submit", (event) => {
  event.preventDefault();
  loadFindings().catch(handleRequestError);
});

elements.engagementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const project = requireProject();
  const data = new FormData(elements.engagementForm);
  elements.engagementMessage.textContent = "";
  try {
    await apiRequest(`/api/v1/projects/${project.project_id}/engagements`, {
      method: "POST",
      body: JSON.stringify({
        name: data.get("name"),
        authorization_reference: data.get("authorization_reference"),
        valid_from: data.get("valid_from"),
        valid_until: data.get("valid_until"),
        allowed_targets: targetLines(data.get("allowed_targets")),
        excluded_targets: targetLines(data.get("excluded_targets")),
      }),
    });
    elements.engagementForm.reset();
    elements.engagementMessage.textContent = "Engagement gespeichert.";
    await loadEngagements();
  } catch (error) {
    elements.engagementMessage.textContent = error.message;
  }
});

elements.runsRefresh.addEventListener("click", () => {
  loadRuns().catch(handleRequestError);
});

initializeShell();
updateImportForm();
loadSession();
