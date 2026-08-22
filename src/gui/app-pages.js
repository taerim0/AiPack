// The read-only browse pages plus the landing/pack-start page, split out
// of app.js -- see app-core.js's header comment for the overall file
// split and load order. This file: renderLanding() (open-existing-project
// form + new-pack form + recent-projects list), renderOverview(),
// renderFiles(), renderRelationships() (post-pack counterpart to the pack
// review flow's relationship section, reusing app-graph.js's tree
// components against an already-saved project), renderFileDetail(), and
// renderSearch().
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
  const noLlmInput = el("input", { type: "checkbox" });
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
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:6px" }, [
      noLlmInput,
      el("span", { text: "LLM 사용 안 함 (GEMINI_API_KEY 불필요 -- 요약은 시그니처/의존성만으로 자동 생성, 코딩 룰/AI 가이드 생략)" }),
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
