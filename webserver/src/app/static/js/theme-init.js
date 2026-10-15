// Loaded synchronously in <head> so the saved theme applies before first paint.
(() => {
  try {
    const savedTheme = localStorage.getItem("greyartifact-theme");
    if (savedTheme === "light" || savedTheme === "dark") {
      document.documentElement.dataset.theme = savedTheme;
    }
  } catch (_error) {
    document.documentElement.dataset.theme = "dark";
  }
})();
