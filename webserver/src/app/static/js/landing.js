import { hasAccessToken } from "./shared/api.js";
import { initializeThemeToggle } from "./shared/shell.js";

// The token lives in session storage, so a signed-in visitor goes straight on
// to the dashboard instead of the login page.
if (hasAccessToken()) {
  for (const link of document.querySelectorAll("#landing-session-link, #landing-primary-link")) {
    link.href = "/dashboard";
    link.textContent = "Zum Dashboard";
  }
}

initializeThemeToggle();
