import { apiRequest, clearAccessToken, hasAccessToken } from "./shared/api.js";
import { initializeShell, renderIdentity, setAdminNavigationVisible } from "./shared/shell.js";

const elements = {
  accessPanel: document.querySelector("#status-access-panel"),
  accessTitle: document.querySelector("#status-access-title"),
  accessMessage: document.querySelector("#status-access-message"),
  loginLink: document.querySelector("#status-login-link"),
  app: document.querySelector("#status-app"),
  hero: document.querySelector("#status-hero"),
  headline: document.querySelector("#status-headline-text"),
  generated: document.querySelector("#status-generated"),
  counts: document.querySelector("#status-counts"),
  checks: document.querySelector("#status-checks"),
  refresh: document.querySelector("#status-refresh"),
};

const stateLabels = {
  ok: "OK",
  warning: "Warnung",
  error: "Störung",
  unconfigured: "Nicht eingerichtet",
};
const stateSeverity = { ok: "low", warning: "medium", error: "high", unconfigured: "info" };
const checkMeta = {
  app: { label: "Anwendung", badge: "GA" },
  database: { label: "Datenbank", badge: "DB" },
  object_storage: { label: "Objektspeicher", badge: "S3" },
  backup: { label: "Backup", badge: "BK" },
  tls: { label: "TLS-Zertifikat", badge: "TL" },
  ddns: { label: "DynDNS", badge: "DN" },
  disk: { label: "Plattenplatz", badge: "HD" },
};

const textElement = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
};

const dateTime = (value) => new Date(value).toLocaleString("de-DE");
const age = (hours) => {
  const minutes = Math.round(hours * 60);
  if (minutes < 60) return { value: String(minutes), unit: "min" };
  if (hours < 48) return { value: hours.toFixed(1).replace(".", ","), unit: "h" };
  return { value: String(Math.floor(hours / 24)), unit: "Tage" };
};
const uptime = (seconds) => {
  if (seconds < 3600) return { value: String(Math.floor(seconds / 60)), unit: "min" };
  if (seconds < 172800) return { value: String(Math.floor(seconds / 3600)), unit: "h" };
  return { value: String(Math.floor(seconds / 86400)), unit: "Tage" };
};
const milliseconds = (value) =>
  value < 10 ? value.toFixed(1).replace(".", ",") : String(Math.round(value));
const familyLabels = { ipv4: "IPv4", ipv6: "IPv6" };
const ddnsResults = { "addresses updated": "aktualisiert", "addresses unchanged": "unverändert" };
const gib = (bytes) => `${(bytes / 1024 ** 3).toFixed(0)} GiB`;
const level = (value, warning, error) => (value >= error ? "error" : value >= warning ? "warning" : "ok");
const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;

// Per check: the headline number, its caption, optional meters and detail lines.
const describe = {
  app: (d) => ({
    ...uptime(d.uptime_seconds),
    caption: "Laufzeit seit dem letzten Start",
    lines: [`Gestartet ${dateTime(d.started_at)}`, `Python ${d.python}`],
  }),
  database: (d) => ({
    value: milliseconds(d.latency_ms),
    unit: "ms",
    caption: "Antwortzeit",
    lines: ["Datenbank erreichbar"],
  }),
  object_storage: (d) => ({
    value: milliseconds(d.latency_ms),
    unit: "ms",
    caption: "Antwortzeit",
    lines: [d.bucket ? `Bucket ${d.bucket}` : "Speicher erreichbar"],
  }),
  backup: (d) => ({
    ...age(d.age_hours),
    caption: "seit der letzten Sicherung",
    meters: [
      {
        label: "Alter (Warnung ab 26 h, Störung ab 50 h)",
        ratio: Math.min(d.age_hours / 50, 1),
        level: level(d.age_hours, 26, 50),
      },
    ],
    lines: [
      `Letzte Sicherung ${dateTime(d.latest)}`,
      d.checksums ? "Prüfsummen vorhanden" : "SHA256SUMS fehlt",
      `${plural(d.count, "Sicherung", "Sicherungen")} in ${d.directory}`,
    ],
  }),
  tls: (d) => ({
    value: String(Math.max(Math.floor(d.days_left), 0)),
    unit: "Tage",
    caption: "Restlaufzeit",
    meters: [
      {
        label: "Restlaufzeit von 90 Tagen",
        ratio: Math.min(Math.max(d.days_left / 90, 0), 1),
        level: d.days_left < 3 ? "error" : d.days_left < 14 ? "warning" : "ok",
      },
    ],
    lines: [d.hostname, `Gültig bis ${dateTime(d.not_after)}`, d.issuer ? `Aussteller: ${d.issuer}` : ""],
  }),
  ddns: (d) => ({
    ...age(Math.max(...d.entries.map((entry) => entry.age_hours))),
    caption: "seit dem letzten Update",
    lines: d.entries.map(
      (entry) => `${familyLabels[entry.family] || entry.family}: ${ddnsResults[entry.result] || entry.result}`,
    ),
  }),
  disk: (d) => {
    const measured = d.volumes.filter((volume) => !volume.error);
    const fullest = Math.max(0, ...measured.map((volume) => volume.used_ratio));
    return {
      value: String(Math.round(fullest * 100)),
      unit: "%",
      caption: "höchste Belegung",
      meters: measured.map((volume) => ({
        label: `${volume.path} · ${gib(volume.used_bytes)} von ${gib(volume.total_bytes)}`,
        ratio: volume.used_ratio,
        level: level(volume.used_ratio, 0.85, 0.95),
      })),
      lines: d.volumes.filter((volume) => volume.error).map((volume) => `${volume.path}: ${volume.error}`),
    };
  },
};

const fallback = (check) => {
  const details = check.details;
  if (check.state === "unconfigured") {
    return { value: "–", caption: "nicht eingerichtet", lines: [`${details.setting} in der .env setzen.`] };
  }
  return { value: "–", caption: "keine Messung", lines: [details.message || "Unbekannter Fehler."] };
};

const meterElement = (meter) => {
  const wrapper = textElement("div", "status-meter", "");
  wrapper.dataset.level = meter.level;
  const track = textElement("div", "status-meter-track", "");
  track.setAttribute("role", "img");
  track.setAttribute("aria-label", `${meter.label}: ${Math.round(meter.ratio * 100)} %`);
  const fill = textElement("span", "status-meter-fill", "");
  fill.style.width = `${Math.round(meter.ratio * 1000) / 10}%`;
  track.append(fill);
  wrapper.append(textElement("small", "", meter.label), track);
  return wrapper;
};

const cardElement = (check) => {
  const meta = checkMeta[check.key] || { label: check.key, badge: "··" };
  const view = check.details.message || check.state === "unconfigured"
    ? fallback(check)
    : (describe[check.key] || fallback)(check.details);

  const card = textElement("article", "status-card", "");
  card.dataset.state = check.state;

  const heading = textElement("div", "metric-heading", "");
  heading.append(textElement("span", "", meta.label), textElement("span", "status-card-badge", meta.badge));

  const figure = textElement("div", "status-card-figure", "");
  const value = textElement("span", "metric-value", view.value);
  if (view.unit) value.append(textElement("small", "status-card-unit", ` ${view.unit}`));
  const pill = textElement("span", "finding-severity", stateLabels[check.state] || check.state);
  pill.dataset.severity = stateSeverity[check.state] || "info";
  figure.append(value, pill);

  card.append(heading, figure, textElement("p", "status-card-caption", view.caption));
  (view.meters || []).forEach((meter) => card.append(meterElement(meter)));
  const lines = (view.lines || []).filter(Boolean);
  if (lines.length) {
    const list = textElement("ul", "status-card-lines", "");
    lines.forEach((line) => list.append(textElement("li", "", line)));
    card.append(list);
  }
  return card;
};

const headlineFor = (counts) => {
  if (counts.error) return `${plural(counts.error, "Störung", "Störungen")} erkannt`;
  if (counts.warning) return plural(counts.warning, "Warnung", "Warnungen");
  return "Alle Systeme betriebsbereit";
};

const renderStatus = (payload) => {
  const counts = { ok: 0, warning: 0, error: 0, unconfigured: 0 };
  payload.checks.forEach((check) => {
    counts[check.state] = (counts[check.state] || 0) + 1;
  });
  elements.hero.dataset.state = payload.overall;
  elements.headline.textContent = headlineFor(counts);
  elements.generated.textContent =
    `${plural(payload.checks.length, "Prüfung", "Prüfungen")} · zuletzt ${dateTime(payload.generated_at)}`;
  elements.counts.replaceChildren(
    ...Object.entries(counts)
      .filter(([, count]) => count > 0)
      .map(([state, count]) => {
        const chip = textElement("span", "status-count", "");
        chip.dataset.state = state;
        chip.append(textElement("strong", "", String(count)), textElement("span", "", stateLabels[state]));
        return chip;
      }),
  );
  elements.checks.replaceChildren(...payload.checks.map(cardElement));
};

const showAccessRequired = (title, message, showLogin = true) => {
  elements.app.classList.add("is-hidden");
  elements.accessPanel.classList.remove("is-hidden");
  elements.accessTitle.textContent = title;
  elements.accessMessage.textContent = message;
  elements.loginLink.classList.toggle("is-hidden", !showLogin);
};

const loadStatus = async () => {
  elements.refresh.disabled = true;
  elements.refresh.textContent = "Prüfe …";
  try {
    renderStatus(await apiRequest("/api/v1/system/status"));
  } catch (error) {
    elements.hero.dataset.state = "error";
    elements.headline.textContent = "Status nicht abrufbar";
    elements.generated.textContent = error.message;
  } finally {
    elements.refresh.disabled = false;
    elements.refresh.textContent = "Neu prüfen";
  }
};

const initialize = async () => {
  if (!hasAccessToken()) {
    showAccessRequired("Anmeldung erforderlich.", "Melde dich an, um den Systemstatus zu sehen.");
    return;
  }
  let isAdmin;
  try {
    const [mePayload, manageablePayload] = await Promise.all([
      apiRequest("/api/v1/auth/me"),
      apiRequest("/api/v1/scopes/manageable"),
    ]);
    renderIdentity(mePayload.principal);
    isAdmin = manageablePayload.scopes.length > 0;
    setAdminNavigationVisible(isAdmin);
  } catch (_error) {
    clearAccessToken();
    showAccessRequired("Anmeldung erforderlich.", "Deine Sitzung ist abgelaufen. Melde dich bitte erneut an.");
    return;
  }
  if (!isAdmin) {
    showAccessRequired("Kein Zugriff.", "Der Systemstatus ist nur für Owner und Admins sichtbar.", false);
    return;
  }
  elements.accessPanel.classList.add("is-hidden");
  elements.app.classList.remove("is-hidden");
  await loadStatus();
};

elements.refresh.addEventListener("click", () => loadStatus());
initializeShell();
initialize();
