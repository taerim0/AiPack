// Ziplex GUI frontend, split into a few plain <script> files loaded in
// order by index.html (app-core.js -> app-graph.js -> app-pack.js ->
// app-pages.js -> app-router.js) -- no build step, no bundler, no ES
// modules, so every function here is a plain global shared across all of
// them, the same as when this all lived in one 1250-line app.js. Load
// order only matters for the bootstrap at the bottom of app-router.js
// (the one place anything actually *runs* at top level, via
// DOMContentLoaded/hashchange) -- every other file is just function/const
// declarations, safe to load in any relative order as long as this one
// (the lowest-level shared helpers) comes first.
//
// This file: localStorage-backed state (aif_path/project_path/recent-
// projects list), the api()/apiPost() fetch wrappers, the el()/svgEl()-
// adjacent DOM-builder helpers (el, copyButton, showError, showLoading),
// the native-picker button family (browseButton and friends, backed by
// window.pywebview.api -- see gui_server.py's _Api), and the small
// confidenceLevel()/setStale() display helpers used across every page.

const LS_AIF = "ziplex.aif_path";
const LS_PROJECT = "ziplex.project_path";
const LS_RECENT = "ziplex.recent"; // JSON array of {aif, project, openedAt}, most recent first
const RECENT_MAX = 8;

const app = document.getElementById("app");
const nav = document.getElementById("nav");
const topbar = document.getElementById("topbar");
const staleBadge = document.getElementById("stale-badge");

function getAif() { return localStorage.getItem(LS_AIF) || ""; }
function getProject() { return localStorage.getItem(LS_PROJECT) || ""; }

// "최근 프로젝트" on the landing page (Nielsen's "recognition rather than
// recall" -- a returning user shouldn't have to re-type or re-browse-to a
// path they've already opened once). Keyed by aif_path since that's the
// one required field; project_path travels alongside it for the freshness
// check but isn't itself unique. Best-effort: a private window or a
// browser with site data blocked can throw on either read or write here,
// and an empty/broken list just means "no recents shown", never a crash.
function getRecent() {
  try {
    const raw = JSON.parse(localStorage.getItem(LS_RECENT) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch { return []; }
}

function pushRecent(aif, project) {
  if (!aif) return;
  try {
    const list = getRecent().filter(r => r.aif !== aif);
    list.unshift({ aif, project: project || "", openedAt: Date.now() });
    localStorage.setItem(LS_RECENT, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch { /* storage unavailable -- recent list just stays empty next time */ }
}

function removeRecent(aif) {
  try {
    localStorage.setItem(LS_RECENT, JSON.stringify(getRecent().filter(r => r.aif !== aif)));
  } catch { /* best-effort, see pushRecent */ }
}

function openProject(aif, project) {
  localStorage.setItem(LS_AIF, aif);
  localStorage.setItem(LS_PROJECT, project || "");
  pushRecent(aif, project);
  location.hash = "#/overview";
}

function relativeTime(ms) {
  const mins = Math.round((Date.now() - ms) / 60000);
  if (mins < 1) return "방금";
  if (mins < 60) return `${mins}분 전`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.round(hours / 24)}일 전`;
}

async function api(path, params = {}) {
  const url = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  }
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}

async function apiPost(path, body = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c) node.appendChild(c);
  return node;
}

function copyButton(getText, label = "📋 복사") {
  const btn = el("button", { class: "secondary", text: label });
  btn.addEventListener("click", async () => {
    await navigator.clipboard.writeText(getText());
    btn.textContent = "복사됨 ✓";
    setTimeout(() => (btn.textContent = label), 1200);
  });
  return btn;
}

function showError(err) {
  app.innerHTML = "";
  app.appendChild(el("div", { class: "error", text: String(err.message || err) }));
}

// Visibility of system status (Nielsen heuristic #1): fetches to /api/* are
// local but not instant, and an empty <main> while one is in flight reads
// as "nothing happened" rather than "working on it". Callers clear this
// themselves (another app.innerHTML = "") once real content is ready to
// render -- same pattern renderSearch's inline "검색 중..." already used,
// just factored out so every page-level fetch gets it, not just search.
function showLoading() {
  app.innerHTML = "";
  app.appendChild(el("p", { class: "muted loading", text: "불러오는 중..." }));
}

// pywebview injects window.pywebview.api once the native window is created
// with js_api=... (see gui_server.py's main()) -- absent in --no-window
// mode (plain browser tab), where there's no bridge to a native dialog at
// all, so every browse button below just tells a human to type the path
// instead when the bridge (or this specific method on it) isn't there.
function hasApi(method) {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api[method]);
}

// Shared by the folder/open-file/save-file pickers below -- each just picks
// a different js_api method (see gui_server.py's _Api) and label/message.
function pickerButton(targetInput, apiMethod, label, unavailableMessage) {
  const btn = el("button", { class: "secondary", text: label });
  btn.addEventListener("click", async () => {
    if (!hasApi(apiMethod)) {
      alert(unavailableMessage);
      return;
    }
    const picked = await window.pywebview.api[apiMethod]();
    if (picked) targetInput.value = picked;
  });
  return btn;
}

const PICKER_UNAVAILABLE = "선택 대화상자는 기본 실행 모드(네이티브 창)에서만 사용할 수 있습니다. --no-window로 실행 중이면 경로를 직접 입력해주세요.";

function browseButton(targetInput) {
  return pickerButton(targetInput, "choose_folder", "📁 찾아보기", PICKER_UNAVAILABLE);
}

// aif.json 경로: an existing file to open, so this is an OPEN dialog
// (see gui_server.py's choose_aif_file), filtered to .json.
function browseAifButton(targetInput) {
  return pickerButton(targetInput, "choose_aif_file", "📄 찾아보기", PICKER_UNAVAILABLE);
}

// 출력 경로: a file that doesn't necessarily exist yet -- pack's own
// save_aif() will create it -- so this is a SAVE dialog, not OPEN
// (see gui_server.py's choose_save_file).
function browseSaveButton(targetInput) {
  return pickerButton(targetInput, "choose_save_file", "📄 찾아보기", PICKER_UNAVAILABLE);
}

function confidenceLevel(conf) {
  return conf >= 0.67 ? "high" : conf >= 0.34 ? "medium" : "low";
}

function setStale(stale) {
  if (stale && stale.is_stale) {
    const parts = [];
    if (stale.changed?.length) parts.push(`변경 ${stale.changed.length}`);
    if (stale.added?.length) parts.push(`추가 ${stale.added.length}`);
    if (stale.removed?.length) parts.push(`삭제 ${stale.removed.length}`);
    staleBadge.title = parts.join(", ") || "변경 감지됨";
    staleBadge.classList.remove("hidden");
  } else {
    staleBadge.classList.add("hidden");
  }
}

// Highlights the current section in the sidebar (see index.html's
// data-route attributes) -- a sidebar needs a clear "you are here"
// indicator the way the old top nav-bar's plain hyperlink list never did.
// Called once from app-router.js's route() per navigation, not from each
// individual render*() -- keeping "which section is this route" in one
// place instead of every page needing to know its own nav entry.
function setActiveNav(routeName) {
  for (const a of nav.querySelectorAll("a[data-route]")) {
    a.classList.toggle("active", a.dataset.route === routeName);
  }
}

// Same idea as setActiveNav() above, one level up: the topbar's two links
// are global destinations (start/resume a pack, open options) rather than
// project sections, so they're highlighted independently of the sidebar --
// neither is active while browsing an already-loaded project (Overview/
// Files/...), since that's the sidebar's own territory, not this bar's.
// name=null (browsing pages, or any route this bar doesn't own) clears
// both rather than leaving a stale one lit.
function setActiveTopbar(name) {
  for (const a of topbar.querySelectorAll("a[data-topbar]")) {
    a.classList.toggle("active", a.dataset.topbar === name);
  }
}
