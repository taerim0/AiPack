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
      el("p", { text: t("home.tagline") }),
    ]),
  ]));
}

function renderPackHome() {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const packProjInput = el("input", { type: "text", placeholder: t("pack.form.projectPathPlaceholder") });
  const packOutInput = el("input", { type: "text", placeholder: t("pack.form.outputPathPlaceholder") });
  const noCacheInput = el("input", { type: "checkbox" });
  const noLlmInput = el("input", { type: "checkbox" });
  const packError = el("div", { class: "error hidden" });
  const loadFilesButton = el("button", { class: "secondary", text: t("pack.form.loadFiles") });
  const fileListBox = el("div", { class: "hidden" });
  const packButton = el("button", { class: "hidden", text: t("pack.form.start") });

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
        fileListBox.appendChild(el("p", { class: "muted", text: t("pack.form.noSafeFiles") }));
      } else {
        const selectAll = el("input", { type: "checkbox", checked: "checked" });
        selectAll.checked = true;
        selectAll.addEventListener("change", () => {
          for (const cb of selectableCheckboxes) cb.checked = selectAll.checked;
        });
        fileListBox.appendChild(el("label", { class: "file-checklist-row", style: "font-weight:600" }, [
          selectAll, el("span", { text: t("pack.form.allFiles", { n: data.safe.length }) }),
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
          el("p", { class: "muted", text: t("pack.form.dangerousDetected", { n: data.dangerous.length }) }),
        ]);
        for (const entry of data.dangerous) {
          const cb = el("input", { type: "checkbox", "data-name": entry.file });
          dangerousCheckboxes.push(cb);

          const detail = [el("div", { class: "dangerous-file-reason", text: entry.reason || t("pack.form.dangerousDefaultReason") })];
          if (entry.line && entry.matched_text != null) {
            detail.push(el("div", { class: "dangerous-file-line", text: t("pack.form.dangerousLine", { line: entry.line, text: entry.matched_text }) }));
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
      packError.textContent = t("pack.form.noFilesSelected");
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
    el("h1", { text: t("nav.pack") }),
    el("p", { class: "muted", text: t("pack.form.description") }),
    el("label", { text: t("pack.form.projectPathLabel") }),
    el("div", { class: "input-row" }, [packProjInput, browseButton(packProjInput)]),
    el("label", { text: t("pack.form.outputPathLabel") }),
    el("div", { class: "input-row" }, [packOutInput, browseSaveButton(packOutInput)]),
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:14px" }, [
      noCacheInput,
      el("span", { text: t("pack.form.noCacheLabel") }),
    ]),
    el("label", { style: "display:flex;align-items:center;gap:6px;margin-top:6px" }, [
      noLlmInput,
      el("span", { text: t("pack.form.noLlmLabel") }),
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

  const aifInput = el("input", { type: "text", id: "aif-input", placeholder: t("check.form.aifPlaceholder"), value: getAif() });
  const projInput = el("input", { type: "text", id: "proj-input", placeholder: t("check.form.projectPlaceholder"), value: getProject() });

  const openCard = el("div", { class: "card landing-intro" }, [
    el("h1", { text: t("nav.check") }),
    el("p", { text: t("check.form.description") }),
    el("label", { text: t("check.form.aifLabel") }),
    el("div", { class: "input-row" }, [aifInput, browseAifButton(aifInput)]),
    el("label", { text: t("check.form.projectLabel") }),
    el("div", { class: "input-row" }, [projInput, browseButton(projInput)]),
    el("div", { class: "copy-row" }, [
      el("button", { text: t("check.form.open"), onclick: () => {
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
            badge.textContent = report.is_stale ? t("check.freshness.stale", { n: changedCount }) : t("check.freshness.fresh");
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
    checkChildren.unshift(el("div", { class: "card recent-card" }, [el("h2", { text: t("check.recentTitle") }), recentList]));
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
// a project is loaded, same as renderPackHome()/renderCheck() above. Two
// settings so far: the GUI's own display language (app-i18n.js's
// getLang()/setLang(), localStorage-backed -- purely client-side, so no
// server round-trip the way the output folder below needs) and the
// default output folder new packs save to (settings.py's `output_dir`,
// GET/POST /api/settings) -- ahead of whatever else (per-project
// freshness checks, translating a *packed project's* own content -- see
// the roadmap items this GUI reorg is being driven by) end up living here
// later. Per-project folder pins aren't edited here at all: typing an
// explicit path in renderPackHome()'s own "출력 경로" field is what sets
// one (see pack_service.start_pack_job()) -- this page only ever touches
// the global fallback every *unpinned* project follows.
function renderOptions() {
  nav.classList.add("hidden");
  app.innerHTML = "";

  const outputDirInput = el("input", { type: "text", placeholder: t("options.outputDirPlaceholder") });
  const saveButton = el("button", { text: t("options.save") });
  const savedNote = el("span", { class: "muted hidden", text: t("options.saved") });
  const errorBox = el("div", { class: "error hidden" });

  // GUI display-language switcher (app-i18n.js) -- ko/en only for now, easy
  // to add more later since every string in this app is already keyed
  // through t(), not hardcoded per call site. Re-running route() after a
  // change re-renders whatever page is current (this one included) in the
  // new language; applyStaticI18n() separately re-translates index.html's
  // own static topbar/sidebar markup, which no render*() call touches.
  const langSelect = el("select", {}, [
    el("option", { value: "ko", text: "한국어" }),
    el("option", { value: "en", text: "English" }),
  ]);
  langSelect.value = getLang();
  langSelect.addEventListener("change", () => {
    setLang(langSelect.value);
    applyStaticI18n();
    route();
  });

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
      el("h1", { text: t("nav.options") }),
    ]),
    el("div", { class: "card" }, [
      el("h2", { text: t("options.languageTitle") }),
      el("div", { class: "input-row" }, [langSelect]),
    ]),
    el("div", { class: "card" }, [
      el("h2", { text: t("options.outputDirTitle") }),
      el("p", { class: "muted", text: t("options.outputDirDescription") }),
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
    // named `tok`, not `t` -- this file's own t() (app-i18n.js) would
    // otherwise be shadowed inside this callback's scope.
    const tokenRows = Object.entries(data.tokens || {}).map(([model, tok]) =>
      el("tr", {}, [
        el("td", { text: model }),
        el("td", { text: `${tok.original} → ${tok.compressed}` }),
        el("td", { text: `${tok.saved_pct}%` }),
      ])
    );

    const summaryText = () =>
      `# ${data.project.name}\n\n${data.project.prompt || ""}\n\n## Rules\n` +
      (data.rules || []).map(r => `- ${r}`).join("\n");

    app.innerHTML = "";
    app.appendChild(el("div", { class: "card" }, [
      el("h1", { text: data.project.name || t("overview.untitled") }),
      el("h2", { text: t("overview.fileCount", { n: data.file_count }) }),
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

    const filterInput = el("input", { type: "text", placeholder: t("files.searchPlaceholder") });
    const tbody = el("tbody");

    // null = original (server) order; otherwise toggled asc/desc on header
    // click -- e.g. sorting by confidence ascending to triage the worst
    // summaries first is a real workflow this table couldn't support before.
    let sortKey = null;
    let sortDir = 1;
    function sortArrow(key) { return sortKey === key ? (sortDir === 1 ? " ▲" : " ▼") : ""; }
    const nameTh = el("th", { text: t("files.nameHeader", { arrow: sortArrow("name") }), class: "sortable" });
    const confTh = el("th", { text: t("files.confidenceHeader", { arrow: sortArrow("confidence") }), class: "sortable" });
    for (const [th, key] of [[nameTh, "name"], [confTh, "confidence"]]) {
      th.addEventListener("click", () => {
        sortDir = sortKey === key ? -sortDir : 1;
        sortKey = key;
        nameTh.textContent = t("files.nameHeader", { arrow: sortArrow("name") });
        confTh.textContent = t("files.confidenceHeader", { arrow: sortArrow("confidence") });
        draw();
      });
    }
    const table = el("table", {}, [
      el("thead", {}, el("tr", {}, [nameTh, el("th", { text: t("files.summaryHeader") }), confTh])),
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
      section.appendChild(el("button", { class: "secondary", text: t("pack.review.backToTree"), onclick: showTreeOverview }));
      section.appendChild(relEditor.el);
    }

    showTreeOverview();

    app.innerHTML = "";
    app.appendChild(el("div", { class: "card" }, [
      el("h1", { text: t("pack.review.fileRelations") }),
      el("p", { class: "muted", text: t("relationships.help") }),
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
      if (!names.length) return el("p", { class: "muted", text: t("fileDetail.none") });
      return el("ul", { class: "file-list" }, names.map(n =>
        el("li", {}, el("a", { href: `#/files/${encodeURIComponent(n)}`, text: n }))
      ));
    }

    const fullText = () => `# ${name}\n\n${info.summary || ""}\n\n\`\`\`\n${detail.compressed}\n\`\`\``;

    app.innerHTML = "";
    app.appendChild(el("div", { class: "card" }, [
      el("h1", { text: name }),
      el("p", { text: info.summary || "" }),
      el("h3", { text: t("fileDetail.dependents") }), fileList(dependents),
      el("h3", { text: t("fileDetail.blastRadius") }), fileList(blastRadius),
      el("h3", { text: "Detail" }),
      el("pre", { text: detail.compressed || t("fileDetail.noContent") }),
      el("div", { class: "copy-row" }, copyButton(fullText, t("fileDetail.copyAll"))),
    ]));
  } catch (e) { showError(e); }
}

function renderSearch() {
  nav.classList.remove("hidden");
  app.innerHTML = "";

  const patternInput = el("input", { type: "text", placeholder: t("search.patternPlaceholder") });
  const ctxInput = el("input", { type: "text", value: "0", style: "width:60px" });
  const ignoreCaseInput = el("input", { type: "checkbox" });
  const results = el("div");

  async function run() {
    const pattern = patternInput.value.trim();
    if (!pattern) return;
    results.innerHTML = t("search.searching");
    try {
      const matches = await api("/api/search", {
        project_path: getProject(),
        pattern,
        context_lines: ctxInput.value || 0,
        ignore_case: ignoreCaseInput.checked,
      });
      results.innerHTML = "";
      if (!matches.length) { results.appendChild(el("p", { class: "muted", text: t("search.noResults") })); return; }
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
    el("button", { text: t("search.button"), onclick: run }),
  ]));
  app.appendChild(results);
}
