import { clearAccessToken } from "./api.js";

export const initials = (name) => {
  const letters = name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return letters || "GA";
};

const setHidden = (selector, hidden) => {
  document.querySelector(selector)?.classList.toggle("is-hidden", hidden);
};

const closeAccountMenu = () => {
  const toggle = document.querySelector("#account-menu-toggle");
  const popover = document.querySelector("#account-menu-popover");
  if (!toggle || !popover) return;
  toggle.setAttribute("aria-expanded", "false");
  popover.classList.add("is-hidden");
};

const setNavigationOpen = (open) => {
  const toggle = document.querySelector("#nav-toggle");
  const navigation = document.querySelector("#main-navigation");
  if (!toggle || !navigation) return;
  navigation.classList.toggle("is-open", open);
  toggle.setAttribute("aria-expanded", String(open));
  toggle.setAttribute("aria-label", open ? "Navigation schließen" : "Navigation öffnen");
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

export const initializeThemeToggle = () => {
  const themeElements = {
    icon: document.querySelector("#theme-icon"),
    label: document.querySelector("#theme-label"),
    toggle: document.querySelector("#theme-toggle"),
  };
  applyTheme(document.documentElement.dataset.theme || "dark", themeElements, false);
  themeElements.toggle.addEventListener("click", () => {
    const nextTheme =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme, themeElements);
  });
};

export const initializeShell = () => {
  const date = document.querySelector("#current-date");
  const accountMenu = document.querySelector("#account-menu");
  const accountToggle = document.querySelector("#account-menu-toggle");
  const accountPopover = document.querySelector("#account-menu-popover");
  const logoutButton = document.querySelector("#logout-button");
  const navToggle = document.querySelector("#nav-toggle");
  const navigation = document.querySelector("#main-navigation");

  date.textContent = new Intl.DateTimeFormat("de-DE", {
    dateStyle: "long",
  }).format(new Date());
  initializeThemeToggle();
  accountToggle.addEventListener("click", () => {
    const open = accountPopover.classList.contains("is-hidden");
    accountPopover.classList.toggle("is-hidden", !open);
    accountToggle.setAttribute("aria-expanded", String(open));
  });
  navToggle?.addEventListener("click", () => {
    setNavigationOpen(!navigation.classList.contains("is-open"));
  });
  navigation?.addEventListener("click", (event) => {
    if (event.target.closest("a")) setNavigationOpen(false);
  });
  document.addEventListener("click", (event) => {
    if (!accountMenu.contains(event.target)) closeAccountMenu();
    if (
      navigation?.classList.contains("is-open") &&
      !navigation.contains(event.target) &&
      !navToggle.contains(event.target)
    ) {
      setNavigationOpen(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (navigation?.classList.contains("is-open")) {
      setNavigationOpen(false);
      navToggle.focus();
      return;
    }
    closeAccountMenu();
    accountToggle.focus();
  });
  logoutButton.addEventListener("click", () => {
    clearAccessToken();
    window.location.assign("/");
  });
};

export const renderIdentity = (principal) => {
  const visibleName = principal.display_name || principal.username;
  document.querySelector("#session-label").textContent = visibleName;
  document.querySelector("#avatar").textContent = initials(visibleName);
  document.querySelector("#account-menu-name").textContent = visibleName;
  document.querySelector("#account-menu-username").textContent = `@${principal.username}`;
  document
    .querySelector("#account-menu-toggle")
    .setAttribute("aria-label", `Kontomenü für ${visibleName} öffnen`);
  setHidden("#account-login-link", true);
  setHidden("#account-profile-link", false);
  setHidden("#logout-button", false);
};

export const renderAnonymousIdentity = () => {
  document.querySelector("#session-label").textContent = "Nicht angemeldet";
  document.querySelector("#avatar").textContent = "GA";
  document.querySelector("#account-menu-name").textContent = "Nicht angemeldet";
  document.querySelector("#account-menu-username").textContent = "Gast";
  document
    .querySelector("#account-menu-toggle")
    .setAttribute("aria-label", "Kontomenü öffnen");
  setHidden("#account-login-link", false);
  setHidden("#account-profile-link", true);
  setHidden("#logout-button", true);
  setAdminNavigationVisible(false);
};

export const setAdminNavigationVisible = (visible) => {
  setHidden("#admin-nav-link", !visible);
  setHidden("#status-nav-link", !visible);
};
