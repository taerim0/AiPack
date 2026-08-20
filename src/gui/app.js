// Ziplex GUI frontend. No build step, no framework: a hand-rolled
// hash router over plain fetch() calls to /api/* (see gui_server.py).
// State (aif_path/project_path) lives in localStorage, not on the server --
// gui_server.py's routes are all stateless, same as mcp_server.py's tools.

const LS_AIF = "ziplex.aif_path";
const LS_PROJECT = "ziplex.project_path";

const app = document.getElementById("app");
const nav = document.getElementById("nav");
const staleBadge = document.getElementById("stale-badge");

function getAif() { return localStorage.getItem(LS_AIF) || ""; }
function getProject() { return localStorage.getItem(LS_PROJECT) || ""; }

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

// pywebview injects window.pywebview.api once the native window is created
// with js_api=... (see gui_server.py's main()) -- absent in --no-window
// mode (plain browser tab), where there's no bridge to a native dialog at
// all, so the browse button just tells a human to type the path instead.
function hasFolderPicker() {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api.choose_folder);
}

function browseButton(targetInput) {
  const btn = el("button", { class: "secondary", text: "📁 찾아보기" });
  btn.addEventListener("click", async () => {
    if (!hasFolderPicker()) {
      alert("폴더 선택 대화상자는 기본 실행 모드(네이티브 창)에서만 사용할 수 있습니다. --no-window로 실행 중이면 경로를 직접 입력해주세요.");
      return;
    }
    const folder = await window.pywebview.api.choose_folder();
    if (folder) targetInput.value = folder;
  });
  return btn;
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

  const openCard = el("div", { class: "card" }, [
    el("h1", { text: "📦 Ziplex" }),
    el("p", { text: "이미 pack된 프로젝트를 둘러보고, 필요한 부분을 복사해 다른 AI 챗에 붙여넣으세요." }),
    el("label", { text: "aif.json 경로" }), aifInput,
    el("label", { text: "프로젝트 폴더 경로 (선택)" }),
    el("div", { class: "input-row" }, [projInput, browseButton(projInput)]),
    el("div", { class: "copy-row" }, [
      el("button", { text: "열기", onclick: () => {
        const aif = aifInput.value.trim();
        const proj = projInput.value.trim();
        if (!aif) { aifInput.focus(); return; }
        localStorage.setItem(LS_AIF, aif);
        localStorage.setItem(LS_PROJECT, proj);
        location.hash = "#/overview";
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
    el("label", { text: "출력 경로 (선택)" }), packOutInput,
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:14px" }, [
      noCacheInput,
      el("span", { text: "이전 pack 캐시 무시 (변경 없는 파일도 전체 재요약)" }),
    ]),
    el("div", { class: "copy-row" }, loadFilesButton),
    fileListBox,
    el("div", { class: "copy-row" }, packButton),
    packError,
  ]);

  app.appendChild(el("div", { class: "landing" }, [openCard, packCard]));

  // prefill from server-side --aif/--project if nothing saved locally yet
  if (!getAif()) {
    api("/api/config").then(cfg => {
      if (cfg.aif_path) aifInput.value = cfg.aif_path;
      if (cfg.project_path) { projInput.value = cfg.project_path; packProjInput.value = cfg.project_path; }
    }).catch(() => {});
  }
}

// Flat per-file editor over a build_tree()-shaped dependency tree
// ({file: {internal: [...], external: [...]}}). `dependencies` is a graph,
// not a tree -- a file can legitimately be depended on by more than one
// other file -- so this edits one edge (file -> target) at a time instead
// of reparenting a whole nested subtree the way an earlier drag-and-drop
// version did (that collapsed ALL of a shared file's references down to
// wherever it got dropped, which is almost never what you want). onLink/
// onUnlink(file, target) are called on each add/remove click; the caller is
// expected to redraw via the returned .setTree() once the server confirms
// the change (see /api/pack/link, /api/pack/unlink in showReviewState).
function renderRelationshipEditor(tree, allFiles, onLink, onUnlink) {
  const box = el("div", { class: "rel-box" });
  let currentTree = tree;

  function fileRow(name) {
    const deps = currentTree[name] || { internal: [], external: [] };
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
      edgeList.appendChild(el("p", { class: "muted", text: "(의존성 없음)" }));
    }

    const targetSelect = el("select", {}, [
      el("option", { value: "", text: "-- 연결할 파일 선택 --" }),
      ...allFiles.filter(f => f !== name && !deps.internal.includes(f)).map(f => el("option", { value: f, text: f })),
    ]);
    const linkButton = el("button", { class: "secondary", text: "+ 연결 추가", onclick: () => {
      if (targetSelect.value) onLink(name, targetSelect.value);
    } });

    return el("div", { class: "rel-file-row" }, [
      el("div", { class: "file-edit-name", text: `📄 ${name}` }),
      edgeList,
      el("div", { class: "toolbar" }, [targetSelect, linkButton]),
    ]);
  }

  function draw() {
    box.innerHTML = "";
    for (const name of allFiles) box.appendChild(fileRow(name));
  }
  draw();

  return { el: box, setTree: (tree) => { currentTree = tree; draw(); } };
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
    const openIt = () => {
      localStorage.setItem(LS_AIF, result.aif_path);
      localStorage.setItem(LS_PROJECT, result.project_path);
      location.hash = "#/overview";
    };
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
      }
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
      // Disable both, not just this one -- otherwise a click here followed
      // fast enough by a click on "완료 및 저장" (still enabled) fires both
      // requests before either response comes back.
      cancelButton.disabled = true;
      submitButton.disabled = true;
      try { await apiPost("/api/pack/cancel", { job_id: jobId }); } catch (e) { /* best-effort */ }
      location.hash = "#/";
    });

    body.appendChild(el("div", {}, [
      el("h3", { text: "프로젝트 이름" }), nameInput,
      el("h3", { text: "AI 가이드" }), promptInput,
      el("h3", { text: "코딩 룰" }), rulesList,
      el("div", { class: "toolbar" }, [newRuleInput, addRuleButton]),
      el("h3", { text: "파일 관계" }),
      el("p", { class: "muted", text: "각 파일마다 \"끊기\"로 특정 의존성 하나만 제거하거나, 드롭다운으로 다른 파일에 대한 의존성을 추가할 수 있습니다. 외부 패키지(📦)는 읽기 전용입니다." }),
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
  app.innerHTML = "";
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
  app.innerHTML = "";
  try {
    const data = await api("/api/files", { aif_path: getAif(), project_path: getProject() });
    setStale(data._stale);
    delete data._stale;

    const filterInput = el("input", { type: "text", placeholder: "파일명/요약 검색..." });
    const tbody = el("tbody");
    const table = el("table", {}, [
      el("thead", {}, el("tr", {}, [el("th", { text: "파일" }), el("th", { text: "요약" }), el("th", { text: "신뢰도" })])),
      tbody,
    ]);

    function draw() {
      const q = filterInput.value.toLowerCase();
      tbody.innerHTML = "";
      for (const [name, info] of Object.entries(data)) {
        if (q && !name.toLowerCase().includes(q) && !(info.summary || "").toLowerCase().includes(q)) continue;
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

    app.appendChild(el("div", { class: "toolbar" }, filterInput));
    app.appendChild(table);
  } catch (e) { showError(e); }
}

async function renderFileDetail(name, params) {
  nav.classList.remove("hidden");
  app.innerHTML = "";
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
