// The read-only browse pages plus the topbar's four global-destination
// pages, split out of app.js -- see app-core.js's header comment for the
// overall file split and load order. This file: renderHome() (route "/",
// the topbar brand/logo's own destination -- deliberately just a logo, no
// real content of its own), renderPackHome() (new-pack form only -- route
// "/pack", topbar's "프로젝트 패킹"), renderCheck() (open-existing-project
// form + recent-projects list -- route "/check", topbar's "프로젝트
// 확인"; these last two used to be one combined landing page at "/" until
// the topbar grew a dedicated slot for each), renderOptions() (topbar's
// fourth destination, currently an empty placeholder), renderOverview(),
// renderFiles(), renderRelationships() (post-pack counterpart to the pack
// review flow's relationship section, reusing app-graph.js's tree
// components against an already-saved project), renderFileDetail(), and
// renderSearch().

// Just the logo -- no content of its own yet. Exists as its own screen
// (rather than redirecting "/" straight to renderPackHome() or
// renderCheck()) purely because the topbar's brand link needs *something*
// to land on that isn't already one of the other three destinations'
// business.
function renderHome() {
  nav.classList.add("hidden");
  app.innerHTML = "";
  app.appendChild(el("div", { class: "landing" }, [
    el("div", { class: "card landing-intro" }, [
      el("h1", { text: "📦 Ziplex" }),
      el("p", { text: "로컬 프로젝트를 압축된 컨텍스트로 요약해, 원본 대신 AI에게 보여주는 도구입니다." }),
    ]),
  ]));
}

function renderPackHome() {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const packProjInput = el("input", { type: "text", placeholder: "예: C:\\path\\to\\my-project" });
  const packOutInput = el("input", { type: "text", placeholder: "선택. 비우면 result/<프로젝트명>.json" });
  const noCacheInput = el("input", { type: "checkbox" });
  const noLlmInput = el("input", { type: "checkbox" });
  const packError = el("div", { class: "error hidden" });
  const loadFilesButton = el("button", { class: "secondary", text: "파일 목록 불러오기" });
  const fileListBox = el("div", { class: "hidden" });
  const packButton = el("button", { class: "hidden", text: "패킹 시작" });

  let selectableCheckboxes = [];
  let dangerousCheckboxes = [];

  loadFilesButton.addEventListener("click", async () => {
    const project_path = packProjInput.value.trim();
    if (!project_path) { packProjInput.focus(); return; }
    packError.classList.add("hidden");
    packButton.classList.add("hidden");
    loadFilesButton.disabled = true;
    try {
      const data = await api("/api/select_files", { project_path });
      // settings.py's resolved default for *this* project (its own pin, or
      // the Options page's global default) -- shown as a placeholder, not
      // filled into the field's actual value, so leaving the field alone
      // still submits blank and re-resolves dynamically at pack time
      // (pack_service.start_pack_job()) rather than being treated as an
      // explicit path that would pin the project to whatever the default
      // just happened to be right now.
      if (data.default_output_path) packOutInput.placeholder = data.default_output_path;
      selectableCheckboxes = [];
      dangerousCheckboxes = [];
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
      }
      // Shown whenever there's anything selectable at all -- safe files,
      // or (an edge case, but a real one: a project that's nothing but
      // fixture/sample files) only a dangerous one a human can still
      // choose to override below.
      if (data.safe.length || data.dangerous.length) {
        packButton.classList.remove("hidden");
      }

      // Sensitive files used to just disappear here with a bare count --
      // "trust us" with no way back for a false positive (a fixture file,
      // a sample .env with placeholder values). Each one now shows *why*
      // it was flagged (scanner.py's scan_file() reason/matched line, not
      // the whole file -- enough to judge it without opening the file) and
      // an opt-in checkbox, unchecked by default and deliberately kept out
      // of `selectableCheckboxes` (so "전체" above can never sweep one in
      // by accident) -- see packButton's click handler below for how the
      // two lists merge back into one selected_files array.
      if (data.dangerous.length) {
        const box = el("div", { class: "dangerous-files" }, [
          el("p", { class: "muted", text: `⚠️ 민감 파일 ${data.dangerous.length}개 감지됨 (기본 제외 -- 아래에서 확인 후 필요하면 포함)` }),
        ]);
        for (const entry of data.dangerous) {
          const cb = el("input", { type: "checkbox", "data-name": entry.file });
          dangerousCheckboxes.push(cb);

          const detail = [el("div", { class: "dangerous-file-reason", text: entry.reason || "민감 정보로 추정됨" })];
          if (entry.line && entry.matched_text != null) {
            detail.push(el("div", { class: "dangerous-file-line", text: `${entry.line}번째 줄: ${entry.matched_text}` }));
          }

          box.appendChild(el("div", { class: "dangerous-file-row" }, [
            el("label", { class: "file-checklist-row" }, [cb, el("span", { text: entry.file })]),
            el("div", { class: "dangerous-file-detail" }, detail),
          ]));
        }
        fileListBox.appendChild(box);
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
    // Naming a dangerous file here is this screen's equivalent of the
    // CLI's review_dangerous_files() prompt -- packager.pack()'s
    // `preselected` handling trusts either list equally (see its own
    // comment), since ticking this box after seeing the same reason/
    // matched-line detail already *is* the human decision that prompt
    // represents, just made through a checkbox instead of a terminal menu.
    const selected_files = [...selectableCheckboxes, ...dangerousCheckboxes]
      .filter(cb => cb.checked).map(cb => cb.dataset.name);
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
        no_llm: noLlmInput.checked,
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
    el("h1", { text: "📦 프로젝트 패킹" }),
    el("p", { class: "muted", text: "파일을 선택해 LLM 요약을 생성한 뒤, 저장 전에 검토/수정할 수 있습니다 (CLI의 대화형 pack과 동일)." }),
    el("label", { text: "프로젝트 폴더 경로" }),
    el("div", { class: "input-row" }, [packProjInput, browseButton(packProjInput)]),
    el("label", { text: "출력 경로 (선택)" }),
    el("div", { class: "input-row" }, [packOutInput, browseSaveButton(packOutInput)]),
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:14px" }, [
      noCacheInput,
      el("span", { text: "이전 pack 캐시 무시 (변경 없는 파일도 전체 재요약)" }),
    ]),
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:6px" }, [
      noLlmInput,
      el("span", { text: "LLM 사용 안 함 (GEMINI_API_KEY 불필요 -- 요약은 시그니처/의존성만으로 자동 생성, 코딩 룰/AI 가이드 생략)" }),
    ]),
    el("div", { class: "copy-row" }, loadFilesButton),
    fileListBox,
    el("div", { class: "copy-row" }, packButton),
    packError,
  ]);

  app.appendChild(el("div", { class: "landing" }, [packCard]));

  // prefill from server-side --project if nothing saved locally yet
  if (!getProject()) {
    api("/api/config").then(cfg => {
      if (cfg.project_path) packProjInput.value = cfg.project_path;
    }).catch(() => {});
  }
}

// The topbar's "프로젝트 확인" destination -- the open-existing-project form
// (aif.json path + optional project folder path, for the freshness check)
// plus the recent-projects list, both of which are about *reaching* an
// already-packed project rather than creating one, unlike renderPackHome()
// above. Recognition-rather-than-recall (Nielsen): a returning user
// shouldn't have to re-type or re-browse-to a path they've already opened.
function renderCheck() {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const aifInput = el("input", { type: "text", id: "aif-input", placeholder: "예: result/my-project.json", value: getAif() });
  const projInput = el("input", { type: "text", id: "proj-input", placeholder: "예: C:\\path\\to\\my-project (선택, 최신 여부 확인용)", value: getProject() });

  const openCard = el("div", { class: "card landing-intro" }, [
    el("h1", { text: "📂 프로젝트 확인" }),
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

  const checkChildren = [openCard];
  const recent = getRecent();
  if (recent.length) {
    const recentList = el("div", { class: "recent-list" }, recent.map(r => {
      // Only checkable when a project folder path was recorded alongside
      // this aif -- openProject()'s second arg is optional, so an entry
      // opened by aif.json path alone has nothing on disk to diff against.
      // /api/freshness (query_service.py's check_freshness()) is a hash
      // comparison, no LLM calls -- cheap enough to fire once per row on
      // every visit to this page without asking first, unlike a full
      // re-pack. Best-effort: a moved/deleted project folder or a missing
      // cache.json just leaves the badge blank instead of breaking the row.
      const badge = el("span", { class: "recent-freshness muted" });
      if (r.project) {
        api("/api/freshness", { project_path: r.project, aif_path: r.aif })
          .then(report => {
            const changedCount = (report.changed?.length || 0) + (report.added?.length || 0) + (report.removed?.length || 0);
            badge.textContent = report.is_stale ? `⚠️ ${changedCount}개 변경` : "✅ 최신";
            badge.classList.toggle("stale", !!report.is_stale);
          })
          .catch(() => {}); // typo'd/moved path, missing cache.json, ... -- leave the badge blank
      }

      const row = el("div", { class: "recent-row" }, [
        el("div", { class: "recent-main", onclick: () => openProject(r.aif, r.project) }, [
          el("div", { class: "recent-aif", text: r.aif }),
          el("div", { class: "recent-meta" }, [
            el("span", { text: `${r.project ? r.project + " · " : ""}${relativeTime(r.openedAt)}` }),
            badge,
          ]),
        ]),
        el("button", { class: "secondary recent-remove", text: "✕", onclick: (e) => {
          e.stopPropagation();
          removeRecent(r.aif);
          row.remove();
        } }),
      ]);
      return row;
    }));
    checkChildren.unshift(el("div", { class: "card recent-card" }, [el("h2", { text: "최근 프로젝트" }), recentList]));
  }
  app.appendChild(el("div", { class: "landing" }, checkChildren));

  // prefill from server-side --aif/--project if nothing saved locally yet
  if (!getAif()) {
    api("/api/config").then(cfg => {
      if (cfg.aif_path) aifInput.value = cfg.aif_path;
      if (cfg.project_path) projInput.value = cfg.project_path;
    }).catch(() => {});
  }
}

// Reachable from the topbar (see index.html/app-router.js) whether or not
// a project is loaded, same as renderPackHome()/renderCheck() above. Only
// one real setting so far -- the default output folder new packs save to
// (settings.py's `output_dir`, GET/POST /api/settings) -- ahead of
// whatever else (per-project freshness checks, a translation toggle -- see
// the roadmap items this GUI reorg is being driven by) end up living here
// later. Per-project folder pins aren't edited here at all: typing an
// explicit path in renderPackHome()'s own "출력 경로" field is what sets
// one (see pack_service.start_pack_job()) -- this page only ever touches
// the global fallback every *unpinned* project follows.
function renderOptions() {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const outputDirInput = el("input", { type: "text", placeholder: "비우면 result/<프로젝트명>.json (Ziplex 설치 폴더 내부)" });
  const saveButton = el("button", { text: "저장" });
  const savedNote = el("span", { class: "muted hidden", text: "저장됨" });
  const errorBox = el("div", { class: "error hidden" });

  saveButton.addEventListener("click", async () => {
    savedNote.classList.add("hidden");
    errorBox.classList.add("hidden");
    saveButton.disabled = true;
    try {
      await apiPost("/api/settings", { output_dir: outputDirInput.value.trim() });
      savedNote.classList.remove("hidden");
    } catch (e) {
      errorBox.textContent = e.message;
      errorBox.classList.remove("hidden");
    } finally {
      saveButton.disabled = false;
    }
  });

  app.appendChild(el("div", { class: "landing" }, [
    el("div", { class: "card landing-intro" }, [
      el("h1", { text: "⚙️ 옵션" }),
    ]),
    el("div", { class: "card" }, [
      el("h2", { text: "기본 저장 폴더" }),
      el("p", { class: "muted", text: "새로 패킹하는 프로젝트가 기본으로 저장될 폴더입니다. 패킹 화면의 \"출력 경로\"에 직접 경로를 입력한 프로젝트는 이 설정 대신 그 경로를 계속 기억해 사용합니다." }),
      el("div", { class: "input-row" }, [outputDirInput, browseButton(outputDirInput)]),
      el("div", { class: "copy-row" }, [saveButton, savedNote]),
      errorBox,
    ]),
  ]));

  api("/api/settings").then(data => { outputDirInput.value = data.output_dir || ""; }).catch(() => {});
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

// Post-pack counterpart to the pack review screen's tree section (see
// showReviewState()): the exact same two components (renderDependencyTree
// Overview, renderRelationshipEditor), just sourced from an already-saved
// project's /api/relationships instead of a live job's review.tree, and
// edited via /api/relationships/link|unlink (pack_service.
// link_saved_relationship()/unlink_saved_relationship() -- no job_id, edits
// aif.json on disk directly) instead of /api/pack/link|unlink. Lets a human
// fix a relationship they notice is wrong after packing without re-running
// the whole pipeline. Low-confidence files (same 0.34 threshold
// confidenceLevel()/corrector.py's triage() use) are flagged in the tree
// the same way a review's needs_review list flags them, since "worth a
// second look" doesn't stop being true just because packing already
// finished.
async function renderRelationships() {
  nav.classList.remove("hidden");
  showLoading();
  const aifPath = getAif();
  try {
    const [relationships, files] = await Promise.all([
      api("/api/relationships", { aif_path: aifPath }),
      api("/api/files", { aif_path: aifPath }),
    ]);
    delete files._stale;
    const allFileNames = Object.keys(relationships).sort();
    const flaggedFileNames = allFileNames.filter(
      name => confidenceLevel(files[name]?.confidence ?? 1.0) === "low"
    );

    let currentTree = relationships;
    const section = el("div", {});
    const editError = el("div", { class: "error hidden" });

    function showTreeOverview() {
      section.innerHTML = "";
      section.appendChild(renderDependencyTreeOverview(currentTree, allFileNames, flaggedFileNames, showEditView));
    }

    function showEditView(selectedFile) {
      section.innerHTML = "";
      let relEditor;
      relEditor = renderRelationshipEditor(
        currentTree,
        allFileNames,
        async (file, target) => {
          editError.classList.add("hidden");
          try {
            const res = await apiPost("/api/relationships/link", { aif_path: aifPath, file, target });
            currentTree = res.relationships;
            relEditor.setTree(currentTree);
          } catch (e) {
            editError.textContent = e.message;
            editError.classList.remove("hidden");
          }
        },
        async (file, target) => {
          editError.classList.add("hidden");
          try {
            const res = await apiPost("/api/relationships/unlink", { aif_path: aifPath, file, target });
            currentTree = res.relationships;
            relEditor.setTree(currentTree);
          } catch (e) {
            editError.textContent = e.message;
            editError.classList.remove("hidden");
          }
        },
        selectedFile
      );
      section.appendChild(el("button", { class: "secondary", text: "← 트리로 돌아가기", onclick: showTreeOverview }));
      section.appendChild(relEditor.el);
    }

    showTreeOverview();

    app.innerHTML = "";
    app.appendChild(el("div", { class: "card" }, [
      el("h1", { text: "파일 관계" }),
      el("p", { class: "muted", text: "▶ 를 클릭해 하위 트리를 접거나 펼치세요. 수정하고 싶은 파일 이름을 클릭하면 편집 화면이 열립니다 -- 변경 사항은 즉시 aif.json에 저장됩니다." }),
      section, editError,
    ]));
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
