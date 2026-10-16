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

const search = document.querySelector("#help-search");
const terms = [...document.querySelectorAll(".help-term")];
const groups = [...document.querySelectorAll(".help-group")];
const count = document.querySelector("#help-count");
const emptyNote = document.querySelector("#help-empty");

const filterTerms = () => {
  const query = search.value.trim().toLocaleLowerCase("de");
  let visible = 0;
  terms.forEach((term) => {
    const match = !query || term.textContent.toLocaleLowerCase("de").includes(query);
    term.hidden = !match;
    if (match) visible += 1;
  });
  groups.forEach((group) => {
    group.hidden = !group.querySelector(".help-term:not([hidden])");
  });
  count.textContent = query
    ? `${visible} von ${terms.length} Begriffen`
    : `${terms.length} Begriffe`;
  emptyNote.hidden = visible > 0;
};

// A jump link (flow chart, "#" anchors, links from other pages) must never
// land on a term the current search has hidden.
window.addEventListener("hashchange", () => {
  const target = document.getElementById(window.location.hash.slice(1));
  if (target?.hidden && search.value) {
    search.value = "";
    filterTerms();
    target.scrollIntoView();
  }
});

search.addEventListener("input", filterTerms);
filterTerms();
