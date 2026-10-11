import { apiFetch, apiRequest } from "../shared/api.js";

const byId = (id) => document.querySelector(`#${id}`);

const elements = {
  root: byId("project-workspace"),
  title: byId("project-workspace-title"),
  description: byId("project-workspace-description"),
  close: byId("project-workspace-close"),
  createForm: byId("project-create-form"),
  createMessage: byId("project-create-message"),
  editForm: byId("project-edit-form"),
  editMessage: byId("project-edit-message"),
  importForm: byId("import-form"),
  importMessage: byId("import-message"),
  importList: byId("import-list"),
  assetFilter: byId("asset-filter-form"),
  assetList: byId("asset-list"),
  evidence: byId("evidence-detail"),
  engagementForm: byId("engagement-form"),
  engagementMessage: byId("engagement-message"),
  engagementList: byId("engagement-list"),
  runList: byId("run-list"),
  runsRefresh: byId("runs-refresh"),
};

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

export const initializeProjectWorkspace = ({ getScopeId, refreshProjects }) => {
  let project = null;

  const requireProject = () => {
    if (!project) throw new Error("Kein Projekt ausgewählt.");
    return project;
  };

  const loadImports = async () => {
    const selected = requireProject();
    const payload = await apiRequest(`/api/v1/projects/${selected.project_id}/imports`);
    elements.importList.replaceChildren();
    if (!payload.imports.length) return empty(elements.importList, "Noch keine Reports.");
    payload.imports.forEach((item) => {
      const row = textElement("article", "record-row", "");
      const copy = document.createElement("div");
      copy.append(
        textElement("strong", "", item.original_filename),
        textElement("small", "", `${item.parser_name} · ${item.status} · ${item.byte_size} Bytes`),
      );
      const actions = textElement("div", "record-actions", "");
      if (item.status !== "completed") {
        const process = textElement("button", "button button-quiet", "Verarbeiten");
        process.type = "button";
        process.addEventListener("click", async () => {
          process.disabled = true;
          try {
            await apiRequest(
              `/api/v1/projects/${selected.project_id}/imports/${item.import_id}/process`,
              { method: "POST" },
            );
            await Promise.all([loadImports(), loadAssets()]);
          } catch (error) {
            elements.importMessage.textContent = error.message;
            await loadImports();
          }
        });
        actions.append(process);
      }
      const download = textElement("button", "button button-quiet", "Original");
      download.type = "button";
      download.addEventListener("click", async () => {
        const response = await apiFetch(
          `/api/v1/projects/${selected.project_id}/imports/${item.import_id}/artifact`,
        );
        if (!response.ok) return;
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

  const showEvidence = async (assetId) => {
    const selected = requireProject();
    const payload = await apiRequest(
      `/api/v1/projects/${selected.project_id}/assets/${assetId}`,
    );
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
    const selected = requireProject();
    const data = new FormData(elements.assetFilter);
    const params = new URLSearchParams();
    if (data.get("q")) params.set("q", data.get("q"));
    if (data.get("type")) params.set("type", data.get("type"));
    const payload = await apiRequest(
      `/api/v1/projects/${selected.project_id}/assets?${params}`,
    );
    elements.assetList.replaceChildren();
    if (!payload.assets.length) return empty(elements.assetList, "Keine passenden Assets.");
    payload.assets.forEach((asset) => {
      const button = textElement("button", "asset-row", "");
      button.type = "button";
      button.append(
        textElement("strong", "", asset.display_value),
        textElement("small", "", asset.type),
      );
      button.addEventListener("click", () => showEvidence(asset.asset_id));
      elements.assetList.append(button);
    });
  };

  const loadEngagements = async () => {
    const selected = requireProject();
    const payload = await apiRequest(
      `/api/v1/projects/${selected.project_id}/engagements`,
    );
    elements.engagementList.replaceChildren();
    if (!payload.engagements.length) return empty(elements.engagementList, "Noch kein Engagement.");
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
    const selected = requireProject();
    const payload = await apiRequest(`/api/v1/projects/${selected.project_id}/runs`);
    elements.runList.replaceChildren();
    if (!payload.runs.length) return empty(elements.runList, "Noch keine Runs.");
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
          await apiRequest(`/api/v1/runs/${run.run_id}/cancel`, { method: "POST" });
          await loadRuns();
        });
        row.append(cancel);
      }
      elements.runList.append(row);
    });
  };

  const open = async (selected) => {
    project = selected;
    elements.title.textContent = selected.name;
    elements.description.textContent = selected.description || "Keine Beschreibung hinterlegt.";
    elements.editForm.elements.slug.value = selected.slug;
    elements.editForm.elements.name.value = selected.name;
    elements.editForm.elements.description.value = selected.description || "";
    elements.root.classList.remove("is-hidden");
    elements.evidence.textContent = "Asset auswählen, um die Herkunft zu sehen.";
    await Promise.all([loadImports(), loadAssets(), loadEngagements(), loadRuns()]);
    elements.root.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  elements.close.addEventListener("click", () => {
    project = null;
    elements.root.classList.add("is-hidden");
  });

  elements.createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    elements.createMessage.textContent = "";
    const data = new FormData(elements.createForm);
    try {
      await apiRequest(`/api/v1/scopes/${getScopeId()}/projects`, {
        method: "POST",
        body: JSON.stringify({
          slug: data.get("slug"),
          name: data.get("name"),
          description: null,
        }),
      });
      elements.createForm.reset();
      elements.createMessage.textContent = "Projekt angelegt.";
      await refreshProjects();
    } catch (error) {
      elements.createMessage.textContent = error.message;
    }
  });

  elements.editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selected = requireProject();
    const data = new FormData(elements.editForm);
    try {
      const payload = await apiRequest(`/api/v1/projects/${selected.project_id}`, {
        method: "PUT",
        body: JSON.stringify({
          slug: data.get("slug"),
          name: data.get("name"),
          description: data.get("description") || null,
        }),
      });
      project = payload.project;
      elements.title.textContent = project.name;
      elements.description.textContent = project.description || "Keine Beschreibung hinterlegt.";
      elements.editMessage.textContent = "Gespeichert.";
      await refreshProjects();
    } catch (error) {
      elements.editMessage.textContent = error.message;
    }
  });

  elements.importForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selected = requireProject();
    elements.importMessage.textContent = "";
    try {
      await apiRequest(`/api/v1/projects/${selected.project_id}/imports`, {
        method: "POST",
        body: new FormData(elements.importForm),
      });
      elements.importForm.reset();
      elements.importMessage.textContent = "Rohartefakt gespeichert; Verarbeitung startet nur auf Klick.";
      await loadImports();
    } catch (error) {
      elements.importMessage.textContent = error.message;
    }
  });

  elements.assetFilter.addEventListener("submit", (event) => {
    event.preventDefault();
    loadAssets();
  });

  elements.engagementForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selected = requireProject();
    const data = new FormData(elements.engagementForm);
    try {
      await apiRequest(`/api/v1/projects/${selected.project_id}/engagements`, {
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

  elements.runsRefresh.addEventListener("click", loadRuns);
  return { open };
};
