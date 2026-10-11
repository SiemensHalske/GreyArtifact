export const initials = (name) => {
  const letters = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return letters || "GA";
};

const applyTheme = (theme, elements, persist = true) => {
  const isDark = theme === "dark";
  document.documentElement.dataset.theme = isDark ? "dark" : "light";
  elements.toggle.setAttribute("aria-pressed", String(isDark));
  elements.toggle.setAttribute(
    "aria-label",
    isDark ? "Helles Farbschema aktivieren" : "Dunkles Farbschema aktivieren",
  );
  elements.icon.textContent = isDark ? "☀" : "☾";
  elements.label.textContent = isDark ? "Hell" : "Dunkel";

  if (persist) {
    try {
      localStorage.setItem("greyartifact-theme", isDark ? "dark" : "light");
    } catch (_error) {
      // The selected theme still applies when browser storage is unavailable.
    }
  }
};

export const initializeShell = () => {
  const themeElements = {
    icon: document.querySelector("#theme-icon"),
    label: document.querySelector("#theme-label"),
    toggle: document.querySelector("#theme-toggle"),
  };
  const date = document.querySelector("#current-date");

  date.textContent = new Intl.DateTimeFormat("de-DE", {
    dateStyle: "long",
  }).format(new Date());
  applyTheme(document.documentElement.dataset.theme || "dark", themeElements, false);
  themeElements.toggle.addEventListener("click", () => {
    const nextTheme =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme, themeElements);
  });
};

export const renderIdentity = (principal) => {
  const visibleName = principal.display_name || principal.username;
  document.querySelector("#session-label").textContent = visibleName;
  document.querySelector("#avatar").textContent = initials(visibleName);
};

export const renderAnonymousIdentity = () => {
  document.querySelector("#session-label").textContent = "Nicht angemeldet";
  document.querySelector("#avatar").textContent = "GA";
};
