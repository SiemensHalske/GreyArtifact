const TOKEN_KEY = "greyartifact-access-token";

const readStoredToken = () => {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch (_error) {
    return null;
  }
};

let accessToken = readStoredToken();

export const hasAccessToken = () => Boolean(accessToken);

export const setAccessToken = (token) => {
  accessToken = token;
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch (_error) {
    // The token remains usable in memory when session storage is unavailable.
  }
};

export const clearAccessToken = () => {
  accessToken = null;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch (_error) {
    // Nothing else is required when session storage is unavailable.
  }
};

export const apiFetch = async (path, options = {}) => {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  return fetch(path, {...options, headers});
};

export const apiRequest = async (path, options = {}) => {
  const response = await apiFetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error?.message || "Anfrage fehlgeschlagen.");
    error.status = response.status;
    error.code = payload.error?.code;
    throw error;
  }
  return payload;
};
