import { apiRequest, clearAccessToken, hasAccessToken } from "./shared/api.js";
import {
  initializeShell,
  renderAnonymousIdentity,
  renderIdentity,
  setAdminNavigationVisible,
} from "./shared/shell.js";

initializeShell();

// The page content is public; signing in only changes the shell.
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
