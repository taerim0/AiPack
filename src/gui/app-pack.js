// The pack job/review flow, split out of app.js -- see app-core.js's
// header comment for the overall file split and load order. This file:
// renderPackJob() -- kicks off/polls a background pack job (gui_server.py's
// /api/pack*), then the "reviewing" state's full correction form (project
// name/guide/rules/summaries, plus the dependency-tree overview + editor
// from app-graph.js for relationships) before submit/finalize.
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
    const flaggedFileNames = review.needs_review.map(e => e.file);

    // Two views sharing one mutable tree: the read-only overview (default,
    // see renderDependencyTreeOverview's own comment for why) and the
    // per-file master-detail editor, swapped into the same container rather
    // than both existing at once. currentTree is the single source of truth
    // either view renders from, updated in place whenever a link/unlink
    // actually commits server-side, so switching back to the overview after
    // an edit reflects it immediately instead of the stale initial tree.
    let currentTree = review.tree;
    const relSection = el("div", {});

    function showTreeOverview() {
      relSection.innerHTML = "";
      relSection.appendChild(renderDependencyTreeOverview(currentTree, allFileNames, flaggedFileNames, showEditView));
    }

    function showEditView(selectedFile) {
      relSection.innerHTML = "";
      let relEditor;
      relEditor = renderRelationshipEditor(
        currentTree,
        allFileNames,
        async (file, target) => {
          treeError.classList.add("hidden");
          try {
            const res = await apiPost("/api/pack/link", { job_id: jobId, file, target });
            currentTree = res.tree;
            relEditor.setTree(currentTree);
          } catch (e) {
            treeError.textContent = e.message;
            treeError.classList.remove("hidden");
          }
        },
        async (file, target) => {
          treeError.classList.add("hidden");
          try {
            const res = await apiPost("/api/pack/unlink", { job_id: jobId, file, target });
            currentTree = res.tree;
            relEditor.setTree(currentTree);
          } catch (e) {
            treeError.textContent = e.message;
            treeError.classList.remove("hidden");
          }
        },
        selectedFile
      );
      relSection.appendChild(el("button", { class: "secondary", text: "← 트리로 돌아가기", onclick: showTreeOverview }));
      relSection.appendChild(relEditor.el);
    }

    showTreeOverview();

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
      el("p", { class: "muted", text: "전체 의존성 트리입니다 (▶ 를 클릭해 하위 트리를 접거나 펼치세요). 수정하고 싶은 파일 이름을 클릭하면 그 파일의 관계 편집 화면이 열립니다 -- 그래프의 다른 파일 노드를 클릭해 이동하거나, \"끊기\"로 의존성을 제거하거나, 검색창에 파일명을 입력해 새 의존성을 추가할 수 있습니다. 외부 패키지(📦)는 읽기 전용입니다." }),
      relSection, treeError,
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
