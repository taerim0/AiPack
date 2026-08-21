// Ziplex GUI frontend. No build step, no framework: a hand-rolled
// hash router over plain fetch() calls to /api/* (see gui_server.py).
// State (aif_path/project_path) lives in localStorage, not on the server --
// gui_server.py's routes are all stateless, same as mcp_server.py's tools.

const LS_AIF = "ziplex.aif_path";
const LS_PROJECT = "ziplex.project_path";
const LS_RECENT = "ziplex.recent"; // JSON array of {aif, project, openedAt}, most recent first
const RECENT_MAX = 8;

const app = document.getElementById("app");
const nav = document.getElementById("nav");
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

// ---- pages ----------------------------------------------------------

function renderLanding() {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const aifInput = el("input", { type: "text", id: "aif-input", placeholder: "예: result/my-project.json", value: getAif() });
  const projInput = el("input", { type: "text", id: "proj-input", placeholder: "예: C:\\path\\to\\my-project (선택, 최신 여부 확인용)", value: getProject() });

  const openCard = el("div", { class: "card landing-intro" }, [
    el("h1", { text: "📦 Ziplex" }),
    el("p", { text: "이미 pack된 프로젝트를 둘러보고, 필요한 부분을 복사해 다른 AI 챗에 붙여넣으세요." }),
    el("label", { text: "aif.json 경로" }),
    el("div", { class: "input-row" }, [aifInput, browseAifButton(aifInput)]),
    el("label", { text: "프로젝트 폴더 경로 (선택)" }),
    el("div", { class: "input-row" }, [projInput, browseButton(projInput)]),
    el("div", { class: "copy-row" }, [
      el("button", { text: "열기", onclick: () => {
        const aif = aifInput.value.trim();
        if (!aif) { aifInput.focus(); return; }
        openProject(aif, projInput.value.trim());
      } }),
    ]),
  ]);

  const packProjInput = el("input", { type: "text", placeholder: "예: C:\\path\\to\\my-project" });
  const packOutInput = el("input", { type: "text", placeholder: "선택. 비우면 result/<프로젝트명>.json" });
  const noCacheInput = el("input", { type: "checkbox" });
  const packError = el("div", { class: "error hidden" });
  const loadFilesButton = el("button", { class: "secondary", text: "파일 목록 불러오기" });
  const fileListBox = el("div", { class: "hidden" });
  const packButton = el("button", { class: "hidden", text: "패킹 시작" });

  let selectableCheckboxes = [];

  loadFilesButton.addEventListener("click", async () => {
    const project_path = packProjInput.value.trim();
    if (!project_path) { packProjInput.focus(); return; }
    packError.classList.add("hidden");
    packButton.classList.add("hidden");
    loadFilesButton.disabled = true;
    try {
      const data = await api("/api/select_files", { project_path });
      selectableCheckboxes = [];
      fileListBox.innerHTML = "";

      if (!data.safe.length) {
        fileListBox.appendChild(el("p", { class: "muted", text: "선택 가능한 안전한 파일이 없습니다." }));
      } else {
        const selectAll = el("input", { type: "checkbox", checked: "checked" });
        selectAll.checked = true;
        selectAll.addEventListener("change", () => {
          for (const cb of selectableCheckboxes) cb.checked = selectAll.checked;
        });
        fileListBox.appendChild(el("label", { class: "file-checklist-row", style: "font-weight:600" }, [
          selectAll, el("span", { text: `전체 ${data.safe.length}개 파일` }),
        ]));

        const list = el("div", { class: "file-checklist" });
        for (const name of data.safe) {
          const cb = el("input", { type: "checkbox", checked: "checked", "data-name": name });
          cb.checked = true;
          selectableCheckboxes.push(cb);
          list.appendChild(el("label", { class: "file-checklist-row" }, [cb, el("span", { text: name })]));
        }
        fileListBox.appendChild(list);
        packButton.classList.remove("hidden");
      }

      if (data.dangerous.length) {
        fileListBox.appendChild(el("p", { class: "muted", text: `⚠️ 민감 파일로 감지되어 제외됨: ${data.dangerous.length}개` }));
      }
      fileListBox.classList.remove("hidden");
    } catch (e) {
      packError.textContent = e.message;
      packError.classList.remove("hidden");
    } finally {
      loadFilesButton.disabled = false;
    }
  });

  packButton.addEventListener("click", async () => {
    const project_path = packProjInput.value.trim();
    const selected_files = selectableCheckboxes.filter(cb => cb.checked).map(cb => cb.dataset.name);
    if (!selected_files.length) {
      packError.textContent = "선택된 파일이 없습니다";
      packError.classList.remove("hidden");
      return;
    }
    packError.classList.add("hidden");
    packButton.disabled = true;
    try {
      const { job_id } = await apiPost("/api/pack", {
        project_path,
        output_path: packOutInput.value.trim(),
        no_cache: noCacheInput.checked,
        selected_files,
      });
      location.hash = `#/pack/${job_id}`;
    } catch (e) {
      packError.textContent = e.message;
      packError.classList.remove("hidden");
      packButton.disabled = false;
    }
  });

  const packCard = el("div", { class: "landing-pack card" }, [
    el("h2", { text: "새 프로젝트 패킹" }),
    el("p", { class: "muted", text: "파일을 선택해 LLM 요약을 생성한 뒤, 저장 전에 검토/수정할 수 있습니다 (CLI의 대화형 pack과 동일)." }),
    el("label", { text: "프로젝트 폴더 경로" }),
    el("div", { class: "input-row" }, [packProjInput, browseButton(packProjInput)]),
    el("label", { text: "출력 경로 (선택)" }),
    el("div", { class: "input-row" }, [packOutInput, browseSaveButton(packOutInput)]),
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:14px" }, [
      noCacheInput,
      el("span", { text: "이전 pack 캐시 무시 (변경 없는 파일도 전체 재요약)" }),
    ]),
    el("div", { class: "copy-row" }, loadFilesButton),
    fileListBox,
    el("div", { class: "copy-row" }, packButton),
    packError,
  ]);

  const landingChildren = [openCard, packCard];
  const recent = getRecent();
  if (recent.length) {
    const recentList = el("div", { class: "recent-list" }, recent.map(r => {
      const row = el("div", { class: "recent-row" }, [
        el("div", { class: "recent-main", onclick: () => openProject(r.aif, r.project) }, [
          el("div", { class: "recent-aif", text: r.aif }),
          el("div", { class: "recent-meta", text: `${r.project ? r.project + " · " : ""}${relativeTime(r.openedAt)}` }),
        ]),
        el("button", { class: "secondary recent-remove", text: "✕", onclick: (e) => {
          e.stopPropagation();
          removeRecent(r.aif);
          row.remove();
        } }),
      ]);
      return row;
    }));
    landingChildren.unshift(el("div", { class: "card recent-card" }, [el("h2", { text: "최근 프로젝트" }), recentList]));
  }
  app.appendChild(el("div", { class: "landing" }, landingChildren));

  // prefill from server-side --aif/--project if nothing saved locally yet
  if (!getAif()) {
    api("/api/config").then(cfg => {
      if (cfg.aif_path) aifInput.value = cfg.aif_path;
      if (cfg.project_path) { projInput.value = cfg.project_path; packProjInput.value = cfg.project_path; }
    }).catch(() => {});
  }
}

function svgEl(tag, attrs = {}, children = []) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c) n.appendChild(c);
  return n;
}

// Keeps the tail of a string rather than the front when it has to be cut --
// last-resort truncation once shortLabels() below has already reduced a
// relative path down to (usually) just its basename, for the rare case
// where even that basename alone is too long for a node box.
function truncateTail(s, max) {
  return s.length <= max ? s : "…" + s.slice(-(max - 1));
}

// Reduces each of `names` (relative paths) to its basename for display --
// "src/very/deep/path/Component.tsx" and "Component.tsx" both read as just
// "Component.tsx" in a mini graph's fixed-width node boxes, since the
// directory prefix was eating into the truncation budget and clipping the
// actual filename (the identifying part) rather than the path (the noisy
// part). Falls back to "parentDir/basename" only for names whose basename
// collides with another name in this same `names` list -- disambiguation is
// scoped to what's actually shown together in one graph, not the whole
// project, so it only kicks in when it would otherwise be genuinely
// ambiguous on screen. The full path is still always available via the
// node's <title> hover tooltip regardless of which label wins here.
function shortLabels(names) {
  const counts = {};
  for (const n of names) {
    const base = n.split("/").pop();
    counts[base] = (counts[base] || 0) + 1;
  }
  const labels = {};
  for (const n of names) {
    const parts = n.split("/");
    const base = parts.pop();
    labels[n] = counts[base] > 1 && parts.length ? `${parts[parts.length - 1]}/${base}` : base;
  }
  return labels;
}

// Small "ego graph" for one file: direct dependents on the left (arrows
// pointing in) and direct dependencies on the right (arrows pointing out),
// capped at REL_GRAPH_MAX_NEIGHBORS per side so a heavily-shared file (a
// utils module with 50 dependents, say) can't blow up the SVG -- the text
// lists below the graph already enumerate everything; this is a visual aid
// for spotting the shape of a file's relationships at a glance, not the
// source of truth. Clicking an internal neighbor node jumps the editor's
// selection to it (via onSelect), so a human can walk the graph instead of
// re-searching the file list for every hop.
const REL_GRAPH_MAX_NEIGHBORS = 6;

function renderMiniGraph(name, parents, children, onSelect) {
  const shownParents = parents.slice(0, REL_GRAPH_MAX_NEIGHBORS);
  const extraParents = parents.length - shownParents.length;
  const shownChildren = children.slice(0, REL_GRAPH_MAX_NEIGHBORS);
  const extraChildren = children.length - shownChildren.length;

  const rows = Math.max(shownParents.length, shownChildren.length, 1);
  const rowH = 26;
  const height = rows * rowH + (extraParents || extraChildren ? 18 : 0) + 20;
  const width = 480;
  const midY = height / 2 - (extraParents || extraChildren ? 9 : 0);
  const midX = width / 2;
  const sideMargin = 8;

  const labels = shortLabels([name, ...shownParents, ...shownChildren.map(c => c.name)]);

  const centerLabel = truncateTail(labels[name], 26);
  const centerW = Math.max(90, centerLabel.length * 6.4 + 24);

  // Two markers, not one: an SVG marker's fill doesn't inherit from the
  // line referencing it, so the accent-colored in/out edges and the muted
  // dashed external edges each need their own arrowhead colored to match.
  function arrowMarker(id, fill) {
    return svgEl("marker", {
      id, viewBox: "0 0 10 10", refX: "9", refY: "5",
      markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse",
    }, [svgEl("path", { d: "M0,0 L10,5 L0,10 z", style: `fill:${fill}` })]);
  }

  const svg = svgEl("svg", { class: "rel-graph", viewBox: `0 0 ${width} ${height}`, width: "100%", height: String(height) }, [
    svgEl("defs", {}, [
      arrowMarker("rel-arrow", "var(--accent)"),
      arrowMarker("rel-arrow-muted", "var(--muted)"),
    ]),
  ]);

  function sideNode(itemName, external, x, y, align) {
    const label = truncateTail(labels[itemName], 20);
    const w = Math.max(70, label.length * 6.1 + 16);
    const rectX = align === "left" ? x : x - w;
    const group = svgEl("g", { class: `rel-node${external ? " external" : ""}` }, [
      svgEl("rect", { x: rectX, y: y - 11, width: w, height: 22, rx: 5 }),
      svgEl("text", { x: rectX + w / 2, y: y + 4, "text-anchor": "middle", text: label }),
      svgEl("title", { text: itemName }),
    ]);
    if (!external && onSelect) {
      group.style.cursor = "pointer";
      group.addEventListener("click", () => onSelect(itemName));
    }
    return { group, edgeX: align === "left" ? rectX + w : rectX };
  }

  function rowY(i) { return midY - ((rows - 1) * rowH) / 2 + i * rowH; }

  shownParents.forEach((p, i) => {
    const y = rowY(i);
    const { group, edgeX } = sideNode(p, false, sideMargin, y, "left");
    svg.appendChild(svgEl("path", {
      class: "rel-edge-line in", "marker-end": "url(#rel-arrow)",
      d: `M${edgeX},${y} C${(edgeX + midX - centerW / 2) / 2},${y} ${(edgeX + midX - centerW / 2) / 2},${midY} ${midX - centerW / 2 - 4},${midY}`,
    }));
    svg.appendChild(group);
  });
  if (extraParents > 0) {
    svg.appendChild(svgEl("text", { class: "rel-graph-more", x: sideMargin, y: rowY(shownParents.length - 1) + rowH, text: `+${extraParents}개 더` }));
  }

  shownChildren.forEach((c, i) => {
    const y = rowY(i);
    const { group, edgeX } = sideNode(c.name, c.external, width - sideMargin, y, "right");
    svg.appendChild(svgEl("path", {
      class: `rel-edge-line out${c.external ? " external" : ""}`, "marker-end": `url(#${c.external ? "rel-arrow-muted" : "rel-arrow"})`,
      d: `M${midX + centerW / 2 + 4},${midY} C${(edgeX + midX + centerW / 2) / 2},${midY} ${(edgeX + midX + centerW / 2) / 2},${y} ${edgeX - 4},${y}`,
    }));
    svg.appendChild(group);
  });
  if (extraChildren > 0) {
    svg.appendChild(svgEl("text", { class: "rel-graph-more", x: width - sideMargin, y: rowY(shownChildren.length - 1) + rowH, "text-anchor": "end", text: `+${extraChildren}개 더` }));
  }

  svg.appendChild(svgEl("g", { class: "rel-node rel-node-center" }, [
    svgEl("rect", { x: midX - centerW / 2, y: midY - 13, width: centerW, height: 26, rx: 6 }),
    svgEl("text", { x: midX, y: midY + 4, "text-anchor": "middle", text: centerLabel }),
    svgEl("title", { text: name }),
  ]));

  return svg;
}

// Master-detail editor over a build_tree()-shaped dependency tree
// ({file: {internal: [...], external: [...]}}). Rendering every file's full
// edge list at once (an earlier version did this) doesn't scale past a
// couple dozen files: the page turns into one long scroll, and each file's
// "add dependency" dropdown lists every other file in the project with no
// way to search it. This instead shows a searchable file list on the left
// and, on the right, only the selected file's own relationships -- an ego
// graph (renderMiniGraph, above) plus the same edit controls the old
// version had, so the amount rendered no longer grows with project size.
// `dependencies` is a graph, not a tree -- a file can legitimately be
// depended on by more than one other file -- so this still edits one edge
// (file -> target) at a time instead of reparenting a whole nested subtree
// the way an earlier drag-and-drop version did (that collapsed ALL of a
// shared file's references down to wherever it got dropped, which is almost
// never what you want). onLink/onUnlink(file, target) are called on each
// add/remove click; the caller is expected to redraw via the returned
// .setTree() once the server confirms the change (see /api/pack/link,
// /api/pack/unlink in showReviewState).
function renderRelationshipEditor(tree, allFiles, onLink, onUnlink, initialSelected) {
  const box = el("div", { class: "rel-master-detail" });
  let currentTree = tree;
  let selected = initialSelected && allFiles.includes(initialSelected) ? initialSelected : (allFiles[0] || null);

  const searchInput = el("input", { type: "text", placeholder: "🔍 파일 검색..." });
  const listPane = el("div", { class: "rel-file-list" });
  const detailPane = el("div", { class: "rel-detail-pane" });

  // Everyone whose own `internal` list points at `name` -- the tree only
  // records outgoing edges per file, so "who depends on me" (shown as the
  // graph's left/parent side) has to be derived by scanning every file
  // rather than looked up directly. Precomputed once per currentTree
  // (buildReverseDeps(), called on setup and again in setTree()) instead of
  // rescanning allFiles from dependentsOf() itself -- drawList() calls it
  // once per visible row, and the search box's "input" listener re-runs
  // drawList() on every keystroke, so an O(n) scan per row made a full
  // relationship-editor redraw O(n²) in the file count.
  let reverseDeps = new Map();
  function buildReverseDeps() {
    reverseDeps = new Map();
    for (const f of allFiles) {
      for (const dep of currentTree[f]?.internal || []) {
        if (!reverseDeps.has(dep)) reverseDeps.set(dep, []);
        reverseDeps.get(dep).push(f);
      }
    }
  }
  function dependentsOf(name) {
    return reverseDeps.get(name) || [];
  }
  buildReverseDeps();

  function selectFile(name) {
    selected = name;
    drawList();
    drawDetail();
  }

  function drawList() {
    const q = searchInput.value.trim().toLowerCase();
    listPane.innerHTML = "";
    let shown = 0;
    for (const name of allFiles) {
      if (q && !name.toLowerCase().includes(q)) continue;
      shown++;
      const deps = currentTree[name] || { internal: [], external: [] };
      const hasEdges = deps.internal.length > 0 || deps.external.length > 0 || dependentsOf(name).length > 0;
      listPane.appendChild(el("div", {
        class: `rel-list-row${name === selected ? " active" : ""}`,
        onclick: () => selectFile(name),
      }, [
        el("span", { class: `rel-dot${hasEdges ? " has-edges" : ""}` }),
        el("span", { class: "rel-list-name", text: name }),
      ]));
    }
    if (!shown) listPane.appendChild(el("p", { class: "muted", style: "padding:10px", text: "일치하는 파일 없음" }));
  }

  function drawDetail() {
    detailPane.innerHTML = "";
    if (!selected) {
      detailPane.appendChild(el("p", { class: "muted", text: "왼쪽에서 파일을 선택하세요." }));
      return;
    }
    const name = selected;
    const deps = currentTree[name] || { internal: [], external: [] };
    const parents = dependentsOf(name);
    const children = [
      ...deps.internal.map(c => ({ name: c, external: false })),
      ...deps.external.map(c => ({ name: c, external: true })),
    ];

    detailPane.appendChild(el("div", { class: "file-edit-name", text: `📄 ${name}` }));
    detailPane.appendChild(renderMiniGraph(name, parents, children, selectFile));

    const edgeList = el("div", { class: "rel-edges" });
    for (const child of deps.internal) {
      const unlinkButton = el("button", { class: "secondary", text: "끊기" });
      unlinkButton.addEventListener("click", () => onUnlink(name, child));
      edgeList.appendChild(el("div", { class: "rel-edge" }, [
        el("span", { text: `→ 📄 ${child}` }), unlinkButton,
      ]));
    }
    for (const ext of deps.external) {
      edgeList.appendChild(el("div", { class: "rel-edge muted" }, el("span", { text: `→ 📦 ${ext}` })));
    }
    if (!deps.internal.length && !deps.external.length) {
      edgeList.appendChild(el("p", { class: "muted", text: "(이 파일이 의존하는 대상 없음)" }));
    }
    detailPane.appendChild(edgeList);

    if (parents.length) {
      detailPane.appendChild(el("p", { class: "muted", text: `이 파일에 의존하는 파일 ${parents.length}개: ${parents.join(", ")}` }));
    }

    const targetListId = "rel-target-options";
    const targetInput = el("input", { type: "text", list: targetListId, placeholder: "🔍 연결할 파일 검색..." });
    const targetOptions = el("datalist", { id: targetListId },
      allFiles.filter(f => f !== name && !deps.internal.includes(f)).map(f => el("option", { value: f })));
    const linkButton = el("button", { class: "secondary", text: "+ 연결 추가", onclick: () => {
      const target = targetInput.value.trim();
      if (target && target !== name) onLink(name, target);
    } });
    detailPane.appendChild(el("div", { class: "toolbar" }, [targetInput, targetOptions, linkButton]));
  }

  searchInput.addEventListener("input", drawList);
  drawList();
  drawDetail();

  box.appendChild(el("div", { class: "rel-list-pane" }, [searchInput, listPane]));
  box.appendChild(detailPane);

  return {
    el: box,
    setTree: (tree) => { currentTree = tree; buildReverseDeps(); drawList(); drawDetail(); },
  };
}

async function renderPackJob(jobId) {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const logPre = el("pre", { class: "pack-log" });
  const statusBadge = el("span", { class: "pack-status running", text: "진행 중..." });
  const body = el("div");
  const card = el("div", { class: "card" }, [
    el("h1", { text: "패킹 진행 상황" }),
    statusBadge,
    el("h3", { text: "로그" }),
    logPre,
    body,
  ]);
  app.appendChild(card);

  function showErrorState(message) {
    statusBadge.className = "pack-status error";
    statusBadge.textContent = "오류";
    body.appendChild(el("div", { class: "error", text: message }));
  }

  function showDoneState(result) {
    statusBadge.className = "pack-status done";
    statusBadge.textContent = "완료";
    const openIt = () => openProject(result.aif_path, result.project_path);
    body.appendChild(el("div", { class: "copy-row" }, [
      el("p", { text: `저장됨: ${result.aif_path}` }),
      el("button", { text: "결과 열기", onclick: openIt }),
    ]));
  }

  // one summary editor row, shared between the "needs review" (flagged,
  // shown with its real signatures so a human can judge the mismatch
  // without opening the file -- same info corrector.py prints to a
  // terminal) and "auto kept" (collapsed, still editable) sections.
  function fileEditor(entry, flagged, summaryInputs) {
    const input = flagged ? el("textarea", { rows: "2" }) : el("input", { type: "text" });
    input.value = entry.summary || "";
    summaryInputs[entry.file] = input;

    const level = confidenceLevel(entry.confidence);
    const header = el("div", { class: "file-edit-header" }, [
      el("span", { class: "file-edit-name", text: entry.file }),
      el("span", { class: `confidence ${level}`, text: entry.confidence.toFixed(2) }),
    ]);
    const children = [header, input];

    if (flagged && entry.signatures && entry.signatures.length) {
      const sigItems = entry.signatures.map(s => el("li", { text: s }));
      if (entry.signatures_more) sigItems.push(el("li", { class: "muted", text: `+ ${entry.signatures_more}개 더` }));
      children.push(el("ul", { class: "file-list" }, sigItems));
    }
    return el("div", { class: `file-edit-row${flagged ? " needs-review" : ""}` }, children);
  }

  async function showReviewState() {
    statusBadge.className = "pack-status reviewing";
    statusBadge.textContent = "검토 대기 중";

    let review;
    try {
      review = await api("/api/pack/review", { job_id: jobId });
    } catch (e) {
      return showErrorState(e.message);
    }

    // Error prevention (Nielsen heuristic #5): name/guide/rules/summary
    // edits below live only in this page's JS state until "완료 및 저장" is
    // clicked -- unlike relationship link/unlink, which hits the server
    // immediately (see add_dependency_in_job/remove_dependency_in_job).
    // A reload or window close here would silently discard all of it with
    // no warning, so guard it the same way any form with unsaved changes
    // should. Cleared on both ways out of this screen (submit succeeds,
    // cancel confirmed) so it doesn't linger and warn on an unrelated later
    // navigation.
    const beforeUnload = (e) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", beforeUnload);

    const nameInput = el("input", { type: "text", value: review.project.name || "" });
    const promptInput = el("textarea", { rows: "3" });
    promptInput.value = review.project.prompt || "";

    let rules = [...review.rules];
    const rulesList = el("ul", { class: "rules-edit" });
    function drawRules() {
      rulesList.innerHTML = "";
      rules.forEach((rule, i) => {
        rulesList.appendChild(el("li", {}, [
          el("span", { text: rule }),
          el("button", { class: "secondary", text: "삭제", onclick: () => { rules.splice(i, 1); drawRules(); } }),
        ]));
      });
    }
    drawRules();

    const newRuleInput = el("input", { type: "text", placeholder: "새 룰 추가" });
    const addRuleButton = el("button", { class: "secondary", text: "추가", onclick: () => {
      const rule = newRuleInput.value.trim();
      if (rule) { rules.push(rule); newRuleInput.value = ""; drawRules(); }
    } });

    const treeError = el("div", { class: "error hidden" });
    const allFileNames = [...review.needs_review, ...review.auto_kept].map(e => e.file).sort();
    // Default the relationship editor's selection to the first flagged file,
    // if any -- a file low-confidence enough to need a summary review is
    // also a reasonable first guess for "worth checking its dependencies too".
    const relEditor = renderRelationshipEditor(
      review.tree,
      allFileNames,
      async (file, target) => {
        treeError.classList.add("hidden");
        try {
          const res = await apiPost("/api/pack/link", { job_id: jobId, file, target });
          relEditor.setTree(res.tree);
        } catch (e) {
          treeError.textContent = e.message;
          treeError.classList.remove("hidden");
        }
      },
      async (file, target) => {
        treeError.classList.add("hidden");
        try {
          const res = await apiPost("/api/pack/unlink", { job_id: jobId, file, target });
          relEditor.setTree(res.tree);
        } catch (e) {
          treeError.textContent = e.message;
          treeError.classList.remove("hidden");
        }
      },
      review.needs_review[0]?.file
    );

    const summaryInputs = {};
    const needsReviewBox = el("div", {}, review.needs_review.length
      ? review.needs_review.map(entry => fileEditor(entry, true, summaryInputs))
      : [el("p", { class: "muted", text: "검토가 필요한 낮은 신뢰도 요약이 없습니다." })]);
    const autoKeptBox = el("div", {}, review.auto_kept.map(entry => fileEditor(entry, false, summaryInputs)));

    const submitError = el("div", { class: "error hidden" });
    const submitButton = el("button", { text: "완료 및 저장" });
    const cancelButton = el("button", { class: "secondary", text: "취소" });

    submitButton.addEventListener("click", async () => {
      submitError.classList.add("hidden");
      submitButton.disabled = true;
      cancelButton.disabled = true;
      const summaries = {};
      for (const [file, input] of Object.entries(summaryInputs)) summaries[file] = input.value.trim();
      try {
        const result = await apiPost("/api/pack/finalize", {
          job_id: jobId,
          project_name: nameInput.value.trim(),
          project_prompt: promptInput.value.trim(),
          rules,
          summaries,
        });
        window.removeEventListener("beforeunload", beforeUnload);
        body.innerHTML = "";
        showDoneState(result);
      } catch (e) {
        submitError.textContent = e.message;
        submitError.classList.remove("hidden");
        submitButton.disabled = false;
        cancelButton.disabled = false;
      }
    });

    cancelButton.addEventListener("click", async () => {
      // Error prevention: this throws away every edit made on this screen
      // (name/guide/rules/summaries -- see the beforeUnload comment above)
      // with no undo, so it gets the same one-step confirmation any
      // destructive action should have rather than firing on a single click.
      if (!confirm("검토 중인 내용을 취소하고 버릴까요? 저장되지 않은 편집 내용이 모두 사라집니다.")) return;
      // Disable both, not just this one -- otherwise a click here followed
      // fast enough by a click on "완료 및 저장" (still enabled) fires both
      // requests before either response comes back.
      cancelButton.disabled = true;
      submitButton.disabled = true;
      window.removeEventListener("beforeunload", beforeUnload);
      try { await apiPost("/api/pack/cancel", { job_id: jobId }); } catch (e) { /* best-effort */ }
      location.hash = "#/";
    });

    body.appendChild(el("div", {}, [
      el("h3", { text: "프로젝트 이름" }), nameInput,
      el("h3", { text: "AI 가이드" }), promptInput,
      el("h3", { text: "코딩 룰" }), rulesList,
      el("div", { class: "toolbar" }, [newRuleInput, addRuleButton]),
      el("h3", { text: "파일 관계" }),
      el("p", { class: "muted", text: "왼쪽에서 파일을 검색해 선택하면 그 파일의 관계만 그래프와 함께 표시됩니다. 그래프의 다른 파일 노드를 클릭하면 그쪽으로 이동합니다. \"끊기\"로 의존성 하나를 제거하거나, 검색창에 파일명을 입력해 새 의존성을 추가하세요. 외부 패키지(📦)는 읽기 전용입니다." }),
      relEditor.el, treeError,
      el("h3", { text: `⚠️ 검토 필요 (${review.needs_review.length}개)` }), needsReviewBox,
      el("h3", { text: `자동 승인됨 (${review.auto_kept.length}개, 필요 시 수정 가능)` }), autoKeptBox,
      el("div", { class: "copy-row" }, [submitButton, cancelButton]),
      submitError,
    ]));
  }

  let since = 0;
  let stopped = false;

  async function poll() {
    if (stopped) return;
    let data;
    try {
      data = await api("/api/pack/status", { job_id: jobId, since });
    } catch (e) {
      stopped = true;
      showErrorState(e.message);
      return;
    }

    if (data.log.length) {
      logPre.textContent += (logPre.textContent ? "\n" : "") + data.log.join("\n");
      logPre.scrollTop = logPre.scrollHeight;
    }
    since = data.log_len;

    // "finalizing" (pack_service.py's transient state while submit_review()
    // commits) is only ever observed here if a reload/second-tab poll lands
    // in that narrow window -- keep polling through it the same as
    // "running" rather than falling into the generic error branch below.
    if (data.state === "running" || data.state === "finalizing") {
      setTimeout(poll, 1000);
      return;
    }

    stopped = true;
    if (data.state === "reviewing") return showReviewState();
    if (data.state === "done") return showDoneState(data.result);
    return showErrorState(data.error || "알 수 없는 오류");
  }
  poll();
}

async function renderOverview() {
  nav.classList.remove("hidden");
  showLoading();
  try {
    const data = await api("/api/overview", { aif_path: getAif(), project_path: getProject() });
    setStale(data._stale);
    const rulesList = el("ul", {}, (data.rules || []).map(r => el("li", { text: r })));
    const tokenRows = Object.entries(data.tokens || {}).map(([model, t]) =>
      el("tr", {}, [
        el("td", { text: model }),
        el("td", { text: `${t.original} → ${t.compressed}` }),
        el("td", { text: `${t.saved_pct}%` }),
      ])
    );

    const summaryText = () =>
      `# ${data.project.name}\n\n${data.project.prompt || ""}\n\n## Rules\n` +
      (data.rules || []).map(r => `- ${r}`).join("\n");

    app.innerHTML = "";
    app.appendChild(el("div", { class: "card" }, [
      el("h1", { text: data.project.name || "(제목 없음)" }),
      el("h2", { text: `파일 ${data.file_count}개` }),
      el("p", { text: data.project.prompt || "" }),
      el("h3", { text: "Rules" }), rulesList,
      el("h3", { text: "Tokens" }),
      el("table", {}, [
        el("thead", {}, el("tr", {}, [el("th", { text: "Model" }), el("th", { text: "Before → After" }), el("th", { text: "Saved" })])),
        el("tbody", {}, tokenRows),
      ]),
      el("div", { class: "copy-row" }, copyButton(summaryText)),
    ]));
  } catch (e) { showError(e); }
}

async function renderFiles() {
  nav.classList.remove("hidden");
  showLoading();
  try {
    const data = await api("/api/files", { aif_path: getAif(), project_path: getProject() });
    setStale(data._stale);
    delete data._stale;

    const filterInput = el("input", { type: "text", placeholder: "파일명/요약 검색..." });
    const tbody = el("tbody");

    // null = original (server) order; otherwise toggled asc/desc on header
    // click -- e.g. sorting by confidence ascending to triage the worst
    // summaries first is a real workflow this table couldn't support before.
    let sortKey = null;
    let sortDir = 1;
    function sortArrow(key) { return sortKey === key ? (sortDir === 1 ? " ▲" : " ▼") : ""; }
    const nameTh = el("th", { text: `파일${sortArrow("name")}`, class: "sortable" });
    const confTh = el("th", { text: `신뢰도${sortArrow("confidence")}`, class: "sortable" });
    for (const [th, key] of [[nameTh, "name"], [confTh, "confidence"]]) {
      th.addEventListener("click", () => {
        sortDir = sortKey === key ? -sortDir : 1;
        sortKey = key;
        nameTh.textContent = `파일${sortArrow("name")}`;
        confTh.textContent = `신뢰도${sortArrow("confidence")}`;
        draw();
      });
    }
    const table = el("table", {}, [
      el("thead", {}, el("tr", {}, [nameTh, el("th", { text: "요약" }), confTh])),
      tbody,
    ]);

    function draw() {
      const q = filterInput.value.toLowerCase();
      let entries = Object.entries(data).filter(([name, info]) =>
        !q || name.toLowerCase().includes(q) || (info.summary || "").toLowerCase().includes(q));
      if (sortKey) {
        entries = entries.slice().sort(([an, ai], [bn, bi]) => {
          const [av, bv] = sortKey === "name" ? [an, bn] : [ai.confidence ?? 1.0, bi.confidence ?? 1.0];
          return av < bv ? -sortDir : av > bv ? sortDir : 0;
        });
      }
      tbody.innerHTML = "";
      for (const [name, info] of entries) {
        const conf = info.confidence ?? 1.0;
        const level = confidenceLevel(conf);
        const row = el("tr", { class: `file-row${level === "low" ? " low-confidence" : ""}`, onclick: () => { location.hash = `#/files/${encodeURIComponent(name)}`; } }, [
          el("td", { text: name }),
          el("td", { text: info.summary || "" }),
          el("td", { class: `confidence ${level}`, text: conf.toFixed(2) }),
        ]);
        tbody.appendChild(row);
      }
    }
    filterInput.addEventListener("input", draw);
    draw();

    app.innerHTML = "";
    app.appendChild(el("div", { class: "toolbar" }, filterInput));
    app.appendChild(table);
  } catch (e) { showError(e); }
}

async function renderFileDetail(name, params) {
  nav.classList.remove("hidden");
  showLoading();
  try {
    const [files, dependents, blastRadius, detail] = await Promise.all([
      api("/api/files", { aif_path: getAif() }),
      api("/api/dependents", { aif_path: getAif(), file: name }),
      api("/api/blast_radius", { aif_path: getAif(), file: name }),
      api("/api/detail", { aif_path: getAif(), file: name, start_line: params.get("start"), end_line: params.get("end") }),
    ]);
    const info = files[name] || {};

    function fileList(names) {
      if (!names.length) return el("p", { class: "muted", text: "(없음)" });
      return el("ul", { class: "file-list" }, names.map(n =>
        el("li", {}, el("a", { href: `#/files/${encodeURIComponent(n)}`, text: n }))
      ));
    }

    const fullText = () => `# ${name}\n\n${info.summary || ""}\n\n\`\`\`\n${detail.compressed}\n\`\`\``;

    app.innerHTML = "";
    app.appendChild(el("div", { class: "card" }, [
      el("h1", { text: name }),
      el("p", { text: info.summary || "" }),
      el("h3", { text: "Dependents (이 파일에 의존하는 파일)" }), fileList(dependents),
      el("h3", { text: "Blast radius (이 파일 변경 시 영향받는 전체 범위)" }), fileList(blastRadius),
      el("h3", { text: "Detail" }),
      el("pre", { text: detail.compressed || "(내용 없음)" }),
      el("div", { class: "copy-row" }, copyButton(fullText, "📋 전체 복사")),
    ]));
  } catch (e) { showError(e); }
}

function renderSearch() {
  nav.classList.remove("hidden");
  app.innerHTML = "";

  const patternInput = el("input", { type: "text", placeholder: "정규식 패턴 (예: TODO|FIXME)" });
  const ctxInput = el("input", { type: "text", value: "0", style: "width:60px" });
  const ignoreCaseInput = el("input", { type: "checkbox" });
  const results = el("div");

  async function run() {
    const pattern = patternInput.value.trim();
    if (!pattern) return;
    results.innerHTML = "검색 중...";
    try {
      const matches = await api("/api/search", {
        project_path: getProject(),
        pattern,
        context_lines: ctxInput.value || 0,
        ignore_case: ignoreCaseInput.checked,
      });
      results.innerHTML = "";
      if (!matches.length) { results.appendChild(el("p", { class: "muted", text: "검색 결과 없음" })); return; }
      for (const m of matches) {
        const lines = [
          ...m.context_before.map(l => el("div", { class: "ctx-line", text: l })),
          el("div", { class: "match-line", text: m.text }),
          ...m.context_after.map(l => el("div", { class: "ctx-line", text: l })),
        ];
        const loc = el("div", { class: "loc", text: `${m.file}:${m.line}`, onclick: () => {
          const start = Math.max(1, m.line - 5), end = m.line + 5;
          location.hash = `#/files/${encodeURIComponent(m.file)}?start=${start}&end=${end}`;
        } });
        results.appendChild(el("div", { class: "search-result" }, [loc, el("pre", {}, lines)]));
      }
    } catch (e) {
      results.innerHTML = "";
      results.appendChild(el("div", { class: "error", text: e.message }));
    }
  }
  patternInput.addEventListener("keydown", e => { if (e.key === "Enter") run(); });

  app.appendChild(el("div", { class: "toolbar" }, [
    patternInput,
    el("label", { text: "context", style: "margin:0" }), ctxInput,
    el("label", { text: "ignore case", style: "margin:0;display:flex;align-items:center;gap:4px" }, ignoreCaseInput),
    el("button", { text: "검색", onclick: run }),
  ]));
  app.appendChild(results);
}

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
  return renderLanding();
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);
