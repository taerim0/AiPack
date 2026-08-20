"""Background pack-job runner backing gui_server.py's /api/pack* routes.

packager.pack() is long-running (real LLM calls, potentially minutes on a
real project) and talks to the user via print()/input() -- wrong to run
straight inside a Flask request handler. This module runs one pack in a
background thread and gives the routes something to poll and act on: a job
id, a running/reviewing/done/error state, pack()'s own print() lines
captured into a per-job log list, and (once analysis finishes) a pause point
where a human reviews and corrects the result before it's saved.

Interactive parity with the CLI's plain `pack <path>` (no --auto, no
--auto-correct), adapted for a browser instead of a terminal:

  - File selection: select_files() (file/selector.py) reads a number list
    off stdin, which doesn't exist over HTTP. list_selectable_files() runs
    the same collect_files()/scan_files() steps up front so gui_server.py
    can show a human the safe/dangerous split as checkboxes; whatever they
    submit is passed into pack()'s new `preselected` parameter (see
    packager.py), which bypasses both `auto` and select_files() entirely.
  - Correction review: corrector.py's correct_aif() is a chain of input()
    prompts. Here, pack() runs with interactive=False (so a *repeated* LLM
    failure still can't block on stdin -- see handle_llm_failure()'s
    non-interactive path in packager.py; that one gap is a known
    limitation, not something this module works around) but is *not*
    followed by an immediate finalize_aif(). Instead the job pauses in
    state "reviewing" with the raw aif (still carrying signatures/
    dependencies/confidence) attached, mirroring what correct_aif() would
    show a terminal user: project name/prompt, rules, and per-file
    summaries triaged by confidence.triage() into needs-review vs.
    auto-kept. submit_review() applies whatever the human changed through
    edits.py's pure setters -- the same seam corrector.py itself is built
    on -- then finalizes and saves, exactly like correct_aif() does at the
    end of its own flow.
  - Relationship editing: corrector.py's correct_relationships() is a
    number-prompt loop over file/relationship.py's move_file() -- reparent
    one file under another, stripping it from every existing reference
    first. The GUI deliberately does *not* mirror that: `dependencies` is a
    graph (a file can have more than one real parent, and cycles can
    already legitimately exist from raw Tree-sitter extraction), and an
    earlier drag-and-drop version built on move_file() silently severed a
    shared file's other references whenever one of its occurrences got
    dragged. add_dependency_in_job()/remove_dependency_in_job() wrap
    file/relationship.py's add_dependency()/remove_dependency() instead --
    a per-edge link/unlink pair that only ever touches the one file/target
    edge being edited, never any other file's list. The review payload's
    `tree` (build_tree()'s shape) is what the GUI renders this over: a flat
    per-file list of outgoing edges, each internal one individually
    removable, plus a picker to link a new one.

Jobs live in memory only (module-level dict) -- gone on server restart, same
lifetime as everything else gui_server.py holds (see its `_default_config`).
Fine for a single-user local tool; nothing here is meant to survive past one
GUI session.
"""

import contextlib
import threading
import uuid
from pathlib import Path

import packager
from confidence import triage
from edits import finalize_aif, set_file_summary, set_project_name, set_project_prompt
from file.collector import collect_files
from file.relationship import add_dependency as _add_dependency
from file.relationship import build_tree
from file.relationship import remove_dependency as _remove_dependency
from file.scanner import scan_files
from file.textutil import relative_key as _rel_key

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Same cap corrector.py's terminal prompt uses for a flagged file's shown
# signatures -- enough to judge the mismatch without dumping a huge list.
_SIGNATURES_SHOWN = 10


class _LogWriter:
    """Stands in for stdout during one pack job: buffers partial writes into
    complete lines and appends each to the job's log list under
    `_jobs_lock`. Without this, pack()'s print() calls would go to the
    server process's own stdout, which a polling GUI client has no way to
    read.
    """

    def __init__(self, job: dict):
        self._job = job
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            with _jobs_lock:
                self._job["log"].append(line)
        return len(s)

    def flush(self) -> None:
        pass


def list_selectable_files(project_path: str) -> dict:
    """Runs collect_files()/scan_files() over project_path and returns the
    safe/dangerous split as sorted relative names -- the read-only step a
    GUI file-selection screen calls before a pack job exists at all, so a
    human sees the real file list (and why anything got excluded) instead of
    guessing. Whatever's checked from `safe` on submit becomes
    start_pack_job()'s `selected_files`.
    """
    files = collect_files(project_path)
    scan_result = scan_files(files)
    return {
        "safe": sorted(_rel_key(f, project_path) for f in scan_result["safe"]),
        "dangerous": sorted(_rel_key(f, project_path) for f in scan_result["dangerous"]),
    }


def _build_review(aif: dict) -> dict:
    """The GUI-review-screen shape of an unfinalized aif: project name/
    prompt, rules, and per-file summaries split by confidence.triage() the
    same way corrector.py's correct_aif() splits them for a terminal --
    `needs_review` (low confidence, shown with its real signatures so a
    human can judge the mismatch without opening the file) and `auto_kept`
    (safe to leave alone, but still editable -- nothing here is read-only).
    """
    needs_review, auto_kept = triage(aif["files"])

    def entry(name: str, with_signatures: bool) -> dict:
        data = aif["files"][name]
        out = {
            "file": name,
            "confidence": data.get("confidence", 1.0),
            "summary": data.get("summary", ""),
        }
        if with_signatures:
            sigs = data.get("signatures", [])
            out["signatures"] = sigs[:_SIGNATURES_SHOWN]
            out["signatures_more"] = max(0, len(sigs) - _SIGNATURES_SHOWN)
        return out

    return {
        "project": dict(aif["project"]),
        "rules": list(aif["rules"]),
        "needs_review": [entry(name, with_signatures=True) for name in needs_review],
        "auto_kept": [entry(name, with_signatures=False) for name in auto_kept],
        # build_tree()'s shape: {file: {"internal": [...], "external": [...]}}
        # -- the same data finalize_aif() later ships as aif.json's
        # `relationships`, but fetched here (and recomputed live by
        # add_dependency_in_job()/remove_dependency_in_job() below) so the
        # GUI can render/edit it before the aif is saved.
        "tree": build_tree(aif["files"]),
    }


def _run(job: dict, project_path: str, output_path: str | None, no_cache: bool, selected_files: list[str]) -> None:
    try:
        with contextlib.redirect_stdout(_LogWriter(job)):
            aif = packager.pack(
                project_path, interactive=False, use_cache=not no_cache, preselected=selected_files
            )
            if not aif:
                # pack() returns {} when nothing was selected, or when a
                # repeated LLM failure hit handle_llm_failure()'s
                # non-interactive path (checkpoint saved, run aborted) --
                # either way there's nothing to review; the log already has
                # the specific reason printed into it.
                raise RuntimeError(
                    "패킹이 완료되지 않았습니다 (선택된 파일이 없거나, "
                    "반복된 LLM 오류로 체크포인트에 저장 후 중단됨). 로그를 확인하세요."
                )
        with _jobs_lock:
            job["state"] = "reviewing"
            job["aif"] = aif
            job["review"] = _build_review(aif)
    except Exception as e:
        with _jobs_lock:
            job["state"] = "error"
            job["error"] = str(e)


def start_pack_job(
    project_path: str, output_path: str | None = None, no_cache: bool = False, selected_files: list[str] | None = None
) -> str:
    """Kicks off one pack() run in a background thread and returns its job id
    immediately. selected_files (relative names, from list_selectable_files()'s
    "safe" list) becomes pack()'s `preselected` -- see this module's docstring
    for why file selection has to happen before the job starts rather than
    inside it. The job pauses in state "reviewing" once analysis finishes;
    see get_review()/submit_review().
    """
    job_id = uuid.uuid4().hex
    job = {
        "state": "running",
        "log": [],
        "result": None,
        "error": None,
        "aif": None,
        "review": None,
        "project_path": project_path,
        "output_path": output_path,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    thread = threading.Thread(
        target=_run, args=(job, project_path, output_path, no_cache, selected_files or []), daemon=True
    )
    thread.start()
    return job_id


def get_job_status(job_id: str, since: int = 0) -> dict | None:
    """None if job_id is unknown (typo, or the server restarted since the job
    was started -- jobs don't persist). Otherwise the job's current state
    plus only the log lines from index `since` onward, so a polling client
    can pass back the length it already has instead of re-fetching the whole
    log (potentially thousands of lines on a large project) on every poll.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return {
            "state": job["state"],
            "log": job["log"][since:],
            "log_len": len(job["log"]),
            "result": job["result"],
            "error": job["error"],
        }


def get_review(job_id: str) -> dict | None:
    """None if job_id is unknown or the job hasn't reached "reviewing" yet
    (still running, or already finalized/errored) -- the review payload only
    exists in that one window. See _build_review() for its shape.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["state"] != "reviewing":
            return None
        return job["review"]


def _require_reviewing_job(job_id: str) -> dict:
    """The shared guard behind every mutation on a paused job (link/unlink/
    submit): job_id has to exist and the job has to actually be paused in
    "reviewing" -- anything else means there's no live `aif` dict to mutate.
    Raises ValueError with a message safe to surface straight to the GUI.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise ValueError(f"알 수 없는 job_id: {job_id}")
        if job["state"] != "reviewing":
            raise ValueError(f"이 작업은 검토 대기 상태가 아닙니다 (현재: {job['state']})")
        return job


def add_dependency_in_job(job_id: str, file_name: str, target: str) -> dict:
    """Adds the dependency edge file_name -> target in a "reviewing" job's
    paused aif -- the "link" backend for the GUI review screen's per-edge
    relationship editor, wrapping file/relationship.add_dependency(). Only
    file_name's own edges change; see that function's docstring for why
    that matters (a file can have more than one real parent). Returns the
    recomputed tree (build_tree()'s shape) so the caller can redraw without
    a full get_review() round trip.

    Raises ValueError for an unknown job_id, a job not currently
    "reviewing", or an unknown/self file_name/target; CycleError if the edge
    would create a dependency cycle. Both are left for the caller
    (gui_server.py) to turn into the right HTTP status rather than being
    swallowed here.
    """
    job = _require_reviewing_job(job_id)
    _add_dependency(job["aif"]["files"], file_name, target)
    return build_tree(job["aif"]["files"])


def remove_dependency_in_job(job_id: str, file_name: str, target: str) -> dict:
    """Removes the dependency edge file_name -> target in a "reviewing"
    job's paused aif -- the "unlink" counterpart to add_dependency_in_job(),
    wrapping file/relationship.remove_dependency() the same way. Returns the
    recomputed tree. Raises ValueError for an unknown job_id, a job not
    currently "reviewing", or an unknown file_name.
    """
    job = _require_reviewing_job(job_id)
    _remove_dependency(job["aif"]["files"], file_name, target)
    return build_tree(job["aif"]["files"])


def cancel_job(job_id: str) -> bool:
    """Discards a job waiting in "reviewing" without saving anything.
    Returns False (no-op) if job_id is unknown or it isn't in that state --
    a running job can't be cancelled mid-analysis, and a done/errored one
    has nothing left to cancel.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None or job["state"] != "reviewing":
            return False
        job["state"] = "error"
        job["error"] = "사용자가 취소함"
        job["aif"] = None
        job["review"] = None
    return True


def submit_review(
    job_id: str,
    project_name: str | None = None,
    project_prompt: str | None = None,
    rules: list[str] | None = None,
    summaries: dict[str, str] | None = None,
) -> dict:
    """Applies GUI-submitted corrections to a "reviewing" job's paused aif,
    then finalizes and saves it -- the non-terminal equivalent of
    corrector.py's correct_aif(), built on the same edits.py setters it
    uses. Returns the {"aif_path", "project_path"} result on success.

    Raises ValueError if job_id is unknown or the job isn't currently
    waiting for review (already finalized, still running, or errored/
    cancelled) -- there's nothing valid to apply corrections to in any of
    those states.
    """
    job = _require_reviewing_job(job_id)
    aif = job["aif"]

    if project_name:
        set_project_name(aif, project_name)
    if project_prompt:
        set_project_prompt(aif, project_prompt)
    if rules is not None:
        aif["rules"] = list(rules)
    for name, summary in (summaries or {}).items():
        if summary and name in aif["files"]:
            set_file_summary(aif, name, summary)

    try:
        with contextlib.redirect_stdout(_LogWriter(job)):
            aif = finalize_aif(aif)
            packager.save_aif(aif, job["output_path"])
    except Exception as e:
        with _jobs_lock:
            job["state"] = "error"
            job["error"] = str(e)
            job["aif"] = None
            job["review"] = None
        raise

    result_path = Path(job["output_path"]) if job["output_path"] else packager.RESULT_DIR / f"{aif['project']['name']}.json"
    result = {"aif_path": str(result_path), "project_path": job["project_path"]}
    with _jobs_lock:
        job["state"] = "done"
        job["result"] = result
        job["aif"] = None  # no longer needed, and keeps the job dict small
        job["review"] = None
    return result
