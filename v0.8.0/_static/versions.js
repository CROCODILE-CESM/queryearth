// Adds a version menu under the search box, from the site's versions.json.
// Each version lives in its own folder (v0.1.0/, dev/); the menu keeps the
// reader on the same page when they switch.
(function () {
  const script = document.currentScript.src; // <site>/<version>/_static/versions.js
  const versionRoot = new URL("../", script);
  const siteRoot = new URL("../", versionRoot);
  const current = versionRoot.pathname.split("/").filter(Boolean).pop();
  const page = location.href.slice(versionRoot.href.length);

  function addMenu(versions) {
    const box = document.querySelector(".wy-side-nav-search");
    if (!box || !versions.includes(current)) return;
    const menu = document.createElement("select");
    menu.setAttribute("aria-label", "Documentation version");
    menu.style.marginTop = "0.5em";
    for (const v of versions) {
      const option = new Option(v === "dev" ? "dev (main)" : v, new URL(v + "/" + page, siteRoot).href);
      option.selected = v === current;
      menu.add(option);
    }
    menu.addEventListener("change", () => (location.href = menu.value));
    box.appendChild(menu);
  }

  fetch(new URL("versions.json", siteRoot))
    .then((response) => response.json())
    .then((versions) => {
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => addMenu(versions));
      } else {
        addMenu(versions);
      }
    })
    .catch(() => {}); // a local build has no versions.json: no menu
})();
