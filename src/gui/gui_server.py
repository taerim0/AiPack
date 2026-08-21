"""Ziplex GUI: a local browse/search companion over an already-packed
project, for environments where Claude Code (or MCP generally) isn't
available but a browser-based AI chat is -- see the `ziplex-roadmap` memory
for the full "who is this for" reasoning.

Most of the /api/* routes below are thin adapters over query_service.py
(query params in, JSON out), same core as mcp_server.py, nothing here beyond
that translation -- and still read-only, same as the MCP server. The
exception is the /api/select_files, /api/pack*, and /api/pack/* family:
those are a *write* path, running packager.pack() itself (via
pack_service.py) so a project can be packed from the GUI directly rather
than requiring a prior CLI run. That flow is interactive by default, same as
the CLI's plain `pack <path>` (no --auto, no --auto-correct): a file
selection screen before the job starts, and a correction/review screen
(project name, AI guide, rules, per-file summaries) before anything is
saved -- see pack_service.py's module docstring for the full route-by-route
mapping onto that terminal flow. Everything else stays read-only: a human
uses those pages to look around an already-packed project and copy what's
useful (each page has a Copy button) into a separate web chat by hand -- see
the roadmap memory's "selective file delivery" framing for why that
hand-off is deliberate rather than something this GUI automates.

Runs as a local Flask server wrapped in a native window via pywebview --
not a browser tab, no URL bar -- but the two are decoupled: the Flask app
underneath (`app`) also works standalone via `flask run` or a bare
`app.run()` for anyone who'd rather use their own browser (or during
development, where webview's window can make debugging fiddlier than a
normal browser tab). That decoupling has one real cost: main()'s windowed
branch exposes a `_Api` bridge (js_api=...) so app.js's path fields --
project folder, aif.json, pack output -- get a real OS file/folder-picker
dialog instead of requiring a typed path. pywebview injects that bridge as
`window.pywebview.api` only in the native window, so it's simply absent in
`--no-window`/bare-`flask run` mode, and app.js's picker buttons (see
hasApi()) fall back to asking for a typed path there rather than assuming
the bridge exists.

Binds to 127.0.0.1 only -- there is no --host flag, on purpose. Exposing
this to the network would open local project data (including original
source, via search_project) to anyone who can reach the port; the
`ziplex-roadmap` memory already rejected the equivalent idea (tunneling the
MCP server to the internet) for the same reason.

Run directly:
    python src/gui/gui_server.py [--aif PATH] [--project PATH] [--port 5321]
"""

import argparse
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path

# This file lives one level under src/ (src/gui/), unlike every top-level
# module it imports below (query_service.py, file/) -- a direct `python
# src/gui/gui_server.py` invocation only puts src/gui/ on sys.path[0], not
# src/ itself. Adding src/ (this file's grandparent) before those imports
# reproduces what pytest.ini's `pythonpath = src` already does for tests,
# and what running any top-level script (src/cli.py, src/mcp_server.py)
# gets for free just by living directly in src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request

from gui import pack_service
import query_service
from file.relationship import CycleError

# static_folder="." -- not "gui" -- since index.html/app.js/style.css are
# this file's own siblings now that gui_server.py itself lives in src/gui/.
app = Flask(__name__, static_folder=".", static_url_path="")

# Filled in from CLI args at startup (see main()); read by GET /api/config
# so the frontend can prefill the landing page without a templating layer --
# index.html/app.js stay plain static files this way.
_default_config = {"aif_path": None, "project_path": None}


# query_service's functions open aif_path/project_path straight off disk
# with no validation -- a typo'd path on the landing page is the single most
# likely failure mode this GUI has. Only /api/detail and /api/search had
# their own try/except (for get_detail's/search_project's ValueError);
# without these two handlers, a bad path anywhere else fell through as
# Flask's default 500 HTML page, which api()'s error message in app.js can't
# extract anything useful from ("요청 실패 (500)" with no reason). Registered
# once here instead of adding try/except to every route.
@app.errorhandler(OSError)
def handle_os_error(e):
    return jsonify({"error": f"파일을 열 수 없습니다: {e.filename or e.strerror or e}"}), 404


@app.errorhandler(json.JSONDecodeError)
def handle_bad_json(e):
    return jsonify({"error": f"JSON 파싱 실패: {e}"}), 400


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/config")
def api_config():
    return jsonify(_default_config)


@app.route("/api/select_files")
def api_select_files():
    """The read-only step before a pack job exists: collect + security-scan
    project_path and return the safe/dangerous split as relative names, so
    the GUI can show a human a checklist -- the browser equivalent of
    select_files()'s terminal picker. See pack_service.list_selectable_files().
    """
    project_path = request.args["project_path"]
    if not Path(project_path).is_dir():
        return jsonify({"error": f"프로젝트 폴더를 찾을 수 없습니다: {project_path}"}), 404
    return jsonify(pack_service.list_selectable_files(project_path))


@app.route("/api/pack", methods=["POST"])
def api_pack_start():
    """Kicks off a background pack of project_path (JSON body) and returns
    {"job_id": ...} immediately -- poll /api/pack/status with it. The job
    pauses in state "reviewing" once analysis finishes, same as the CLI's
    plain (non---auto-correct) `pack`; see /api/pack/review and
    /api/pack/finalize below, and pack_service.py's module docstring for the
    full interactive-parity picture.
    """
    data = request.get_json(silent=True) or {}
    project_path = (data.get("project_path") or "").strip()
    if not project_path:
        return jsonify({"error": "project_path가 필요합니다"}), 400
    if not Path(project_path).is_dir():
        return jsonify({"error": f"프로젝트 폴더를 찾을 수 없습니다: {project_path}"}), 404

    selected_files = data.get("selected_files")
    if not selected_files:
        return jsonify({"error": "선택된 파일이 없습니다"}), 400

    output_path = (data.get("output_path") or "").strip() or None
    no_cache = bool(data.get("no_cache"))
    job_id = pack_service.start_pack_job(project_path, output_path, no_cache, selected_files)
    return jsonify({"job_id": job_id})


@app.route("/api/pack/review")
def api_pack_review():
    """The paused job's project/rules/per-file-summary state for a GUI
    correction screen, triaged by confidence the same way corrector.py's
    terminal flow triages it. 404 while the job is still running or once
    it's already been finalized/errored -- the review payload only exists in
    the "reviewing" window.
    """
    job_id = request.args["job_id"]
    review = pack_service.get_review(job_id)
    if review is None:
        return jsonify({"error": f"검토 가능한 작업이 아닙니다: {job_id}"}), 404
    return jsonify(review)


@app.route("/api/pack/link", methods=["POST"])
def api_pack_link():
    """Relationship-editor "link" endpoint: adds the dependency edge `file`
    -> `target` in a "reviewing" job and returns the recomputed tree. See
    pack_service.add_dependency_in_job() -- only `file`'s own edges change,
    unlike the drag-and-drop reparenting this replaced.
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    file_name = data.get("file")
    target = data.get("target")
    if not job_id or not file_name or not target:
        return jsonify({"error": "job_id, file, target가 모두 필요합니다"}), 400
    try:
        tree = pack_service.add_dependency_in_job(job_id, file_name, target)
    except CycleError as e:
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"tree": tree})


@app.route("/api/pack/unlink", methods=["POST"])
def api_pack_unlink():
    """Relationship-editor "unlink" endpoint: removes the dependency edge
    `file` -> `target` in a "reviewing" job and returns the recomputed tree.
    See pack_service.remove_dependency_in_job().
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    file_name = data.get("file")
    target = data.get("target")
    if not job_id or not file_name or not target:
        return jsonify({"error": "job_id, file, target가 모두 필요합니다"}), 400
    try:
        tree = pack_service.remove_dependency_in_job(job_id, file_name, target)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"tree": tree})


@app.route("/api/pack/finalize", methods=["POST"])
def api_pack_finalize():
    """Applies whatever corrections the GUI submitted and saves the result --
    see pack_service.submit_review() for how each field maps onto edits.py's
    setters.
    """
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    if not job_id:
        return jsonify({"error": "job_id가 필요합니다"}), 400
    try:
        result = pack_service.submit_review(
            job_id,
            project_name=data.get("project_name"),
            project_prompt=data.get("project_prompt"),
            rules=data.get("rules"),
            summaries=data.get("summaries"),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify(result)


@app.route("/api/pack/cancel", methods=["POST"])
def api_pack_cancel():
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id")
    if not job_id or not pack_service.cancel_job(job_id):
        return jsonify({"error": f"취소할 수 있는 작업이 아닙니다: {job_id}"}), 404
    return jsonify({"ok": True})


@app.route("/api/pack/status")
def api_pack_status():
    job_id = request.args["job_id"]
    since = request.args.get("since", default=0, type=int)
    status = pack_service.get_job_status(job_id, since)
    if status is None:
        return jsonify({"error": f"알 수 없는 job_id: {job_id}"}), 404
    return jsonify(status)


@app.route("/api/overview")
def api_overview():
    aif_path = request.args["aif_path"]
    project_path = request.args.get("project_path") or None
    return jsonify(query_service.get_overview(aif_path, project_path))


@app.route("/api/files")
def api_files():
    aif_path = request.args["aif_path"]
    project_path = request.args.get("project_path") or None
    return jsonify(query_service.list_files(aif_path, project_path))


@app.route("/api/dependents")
def api_dependents():
    aif_path = request.args["aif_path"]
    file = request.args["file"]
    return jsonify(query_service.get_dependents(aif_path, file))


@app.route("/api/blast_radius")
def api_blast_radius():
    aif_path = request.args["aif_path"]
    file = request.args["file"]
    return jsonify(query_service.get_blast_radius(aif_path, file))


@app.route("/api/detail")
def api_detail():
    aif_path = request.args["aif_path"]
    file = request.args["file"]
    start_line = request.args.get("start_line", type=int)
    end_line = request.args.get("end_line", type=int)
    try:
        compressed = query_service.get_detail(aif_path, file, start_line, end_line)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"compressed": compressed})


@app.route("/api/freshness")
def api_freshness():
    project_path = request.args["project_path"]
    aif_path = request.args["aif_path"]
    return jsonify(query_service.check_freshness(project_path, aif_path))


@app.route("/api/search")
def api_search():
    project_path = request.args["project_path"]
    pattern = request.args["pattern"]
    context_lines = request.args.get("context_lines", default=0, type=int)
    ignore_case = request.args.get("ignore_case", default="false") == "true"
    try:
        results = query_service.search_project(project_path, pattern, context_lines, ignore_case)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(results)


def _find_free_port(preferred: int) -> int:
    """Returns `preferred` if nothing's listening on it yet, otherwise the
    next free port after it (checked up to 50 ports ahead).

    Without this, a port already in use fails inside app.run(), which runs
    in a background thread (see main()) -- that OSError has no way to reach
    main() before it goes on to open a pywebview window pointed at a server
    that never started, silently showing a blank/unreachable window with no
    indication why. Picking a free port up front avoids the failure
    entirely instead of trying to detect and report it after the fact.
    """
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:  # nothing answered -> free
                return port
    raise RuntimeError(f"{preferred}-{preferred + 49} 범위에 사용 가능한 포트가 없습니다")


def main():
    parser = argparse.ArgumentParser(description="Ziplex GUI")
    parser.add_argument("--aif", default=None, help="시작 시 미리 채울 aif.json 경로")
    parser.add_argument("--project", default=None, help="시작 시 미리 채울 프로젝트 폴더 경로")
    parser.add_argument("--port", type=int, default=5321)
    parser.add_argument("--no-window", action="store_true", help="pywebview 창 대신 기본 브라우저로 열기")
    args = parser.parse_args()

    _default_config["aif_path"] = args.aif
    _default_config["project_path"] = args.project

    port = _find_free_port(args.port)
    if port != args.port:
        print(f"⚠️  포트 {args.port}이(가) 사용 중이라 {port}번으로 대신 실행합니다.", flush=True)
    url = f"http://127.0.0.1:{port}/"

    def run_flask():
        app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=run_flask, daemon=True)
    thread.start()

    if args.no_window:
        webbrowser.open(url)
        thread.join()
    else:
        import webview

        _JSON_FILE_TYPES = ("JSON 파일 (*.json)", "모든 파일 (*.*)")

        class _Api:
            """Exposed to the frontend as window.pywebview.api once the
            window below is created with js_api=... -- lets app.js open a
            real OS file/folder-picker dialog instead of requiring a human
            to type a path by hand, for every path field the landing page
            has. Only available in this (default) windowed mode:
            --no-window opens a plain browser tab with no pywebview bridge,
            so app.js falls back to manual entry there (see its hasApi()).
            """

            def choose_folder(self) -> str | None:
                result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
                return result[0] if result else None

            def choose_aif_file(self) -> str | None:
                """The landing page's "aif.json 경로" field -- picks an
                *existing* file, so this is an OPEN dialog. Filtered to
                .json since that's what pack ever writes, but "모든 파일"
                is still offered in case someone renamed/moved it.
                """
                result = webview.windows[0].create_file_dialog(
                    webview.FileDialog.OPEN, file_types=_JSON_FILE_TYPES
                )
                return result[0] if result else None

            def choose_save_file(self) -> str | None:
                """The pack form's "출력 경로" field -- the target doesn't
                exist yet (save_aif() creates it), so this is a SAVE
                dialog, not OPEN: it lets a human pick/type a destination
                filename in a folder they browse to, same as any other
                app's "save as".
                """
                result = webview.windows[0].create_file_dialog(
                    webview.FileDialog.SAVE, save_filename="project.json", file_types=_JSON_FILE_TYPES
                )
                return result[0] if result else None

        window = webview.create_window("Ziplex", url, width=1100, height=800, js_api=_Api())

        def confirm_close_if_reviewing():
            """Registered on window.events.closing (see the pywebview
            source: a handler returning False cancels the close, anything
            else lets it proceed). app.js's beforeunload guard protects an
            in-page reload/navigation during a pack review, but clicking
            this native window's own close button bypasses the DOM
            entirely -- pywebview tears the webview down directly rather
            than navigating it away, so beforeunload never fires. This is
            the same gap closed for --no-window/plain-browser-tab mode by
            the browser's own close-tab prompt; the native window needs its
            own guard because there's no browser chrome to provide one.

            Checks pack_service directly (has_reviewing_job()) instead of
            round-tripping into page JS via evaluate_js() -- calling that
            from a closing handler risks deadlocking against the webview's
            own message loop on some backends, while create_confirmation_dialog
            below is the same safe pattern pywebview's own built-in
            confirm_close option uses internally (a native modal, not a JS
            call).
            """
            if not pack_service.has_reviewing_job():
                return
            return window.create_confirmation_dialog(
                "검토 중인 작업이 있습니다",
                "저장하지 않은 패킹 검토 내용(이름/가이드/룰/요약)이 있습니다. 그래도 닫으시겠습니까?",
            )

        window.events.closing += confirm_close_if_reviewing
        webview.start()


if __name__ == "__main__":
    main()
