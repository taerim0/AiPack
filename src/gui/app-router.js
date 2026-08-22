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

  if (segments[0] === "pack" && segments.length === 2) { setActiveTopbar("pack"); return renderPackJob(segments[1]); }

  // Global destinations the topbar owns -- reachable with or without a
  // project loaded, unlike everything below, which is either the landing
  // page itself or a section of an already-loaded project. Checked before
  // the aif-required guard just below for that reason: "no project loaded
  // yet" should never bounce a request for Options back to landing.
  if (segments[0] === "options") { setActiveTopbar("options"); return renderOptions(); }

  if (!getAif() && segments[0] !== undefined && segments.length) {
    // no project loaded yet -- bounce to landing regardless of requested route
    location.hash = "#/";
    return;
  }

  if (segments.length === 0) { setActiveTopbar("pack"); return renderLanding(); }
  if (segments[0] === "overview") { setActiveTopbar(null); setActiveNav("overview"); return renderOverview(); }
  if (segments[0] === "files" && segments.length === 1) { setActiveTopbar(null); setActiveNav("files"); return renderFiles(); }
  if (segments[0] === "files" && segments.length >= 2) {
    setActiveTopbar(null);
    setActiveNav("files"); // a file's own detail page still belongs to the Files section
    return renderFileDetail(decodeURIComponent(segments.slice(1).join("/")), params);
  }
  if (segments[0] === "search") { setActiveTopbar(null); setActiveNav("search"); return renderSearch(); }
  if (segments[0] === "relationships") { setActiveTopbar(null); setActiveNav("relationships"); return renderRelationships(); }
  setActiveTopbar("pack");
  return renderLanding();
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);
