// The hash router + page bootstrap, split out of app.js -- see
// app-core.js's header comment for the overall file split and load order.
// Loaded last (in index.html's script order) since the two event
// listeners at the bottom are the only top-level code in this whole
// split that actually *runs* immediately rather than just declaring a
// function -- by the time either one can fire, every other script has
// already finished executing and every render* function it calls exists.
// ---- router -----------------------------------------------------------

function route() {
  const raw = location.hash.slice(1) || "/";
  const [path, queryStr] = raw.split("?");
  const params = new URLSearchParams(queryStr || "");
  const segments = path.split("/").filter(Boolean);

  if (segments[0] === "pack" && segments.length === 2) return renderPackJob(segments[1]);

  if (!getAif() && segments[0] !== undefined && segments.length) {
    // no project loaded yet -- bounce to landing regardless of requested route
    location.hash = "#/";
    return;
  }

  if (segments.length === 0) return renderLanding();
  if (segments[0] === "overview") return renderOverview();
  if (segments[0] === "files" && segments.length === 1) return renderFiles();
  if (segments[0] === "files" && segments.length >= 2) {
    return renderFileDetail(decodeURIComponent(segments.slice(1).join("/")), params);
  }
  if (segments[0] === "search") return renderSearch();
  if (segments[0] === "relationships") return renderRelationships();
  return renderLanding();
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);
