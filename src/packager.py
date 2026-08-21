import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from file.collector import collect_files
from file.scanner import scan_files
from file.selector import select_files
from file.textutil import relative_key as _rel_key
from extract.code.extractor import extract_signatures, extract_dependencies, extract_api
from extract.code.compressor import compress_file
from tokenizer import analyze_tokens_with_payload
from llm import analyze_file_summary, analyze_text_summary, analyze_batch_summaries, analyze_rules, analyze_prompt
from freshness import build_manifest, check_freshness
from confidence import estimate_confidence
from config import collection_kwargs

CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoint"
RESULT_DIR = Path(__file__).parent.parent / "result"

# Concurrency used when requesting per-file summaries in parallel.
# Kept conservative with LLM API rate limits in mind — adjust if needed.
MAX_WORKERS = 4

# Files per batched summary request (see llm.analyze_batch_summaries). Trades
# a somewhat larger prompt for far fewer requests -- directly eases the
# rate-limit pressure that drives most first-pack retries, without changing
# MAX_WORKERS' cross-batch parallelism.
BATCH_SIZE = 8


def save_checkpoint(root_path: str, data: dict) -> None:
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    name = Path(root_path).name
    path = CHECKPOINT_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 체크포인트 저장됨: {path}")


def load_checkpoint(root_path: str) -> dict | None:
    name = Path(root_path).name
    path = CHECKPOINT_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_checkpoint(root_path: str) -> None:
    name = Path(root_path).name
    path = CHECKPOINT_DIR / f"{name}.json"
    if path.exists():
        path.unlink()


def handle_llm_failure(
    name: str, field: str, current_aif: dict, root_path: str, interactive: bool = True
) -> str | None:
    """On an LLM call that's exhausted its own internal retries: ask the user
    what to do (retry / type a value / checkpoint and exit), or -- when
    interactive=False, e.g. under `pack --auto-correct` -- skip the prompt
    entirely and behave as if "checkpoint and exit" was chosen. That keeps a
    non-interactive `pack` call from blocking on input() forever (or crashing
    with EOFError, which is what used to happen here under a closed stdin);
    the caller gets a clean {} back and the checkpoint is there to resume
    from once the LLM is behaving again.
    """
    print(f"\n  ⚠️  {name} {field} 생성 실패")

    if not interactive:
        print("  💾 비대화형 모드 → 체크포인트 저장 후 중단")
        save_checkpoint(root_path, current_aif)
        return "EXIT"

    print("  [1] 재시도")
    print("  [2] 직접 입력")
    print("  [3] 저장 후 종료")
    choice = input("  선택: ").strip()

    if choice == "1":
        return None
    elif choice == "2":
        return input(f"  {field} 직접 입력: ").strip()
    elif choice == "3":
        save_checkpoint(root_path, current_aif)
        return "EXIT"

    return None


def _resume_checkpoint_choice(interactive: bool) -> bool:
    """Returns True to resume from a found checkpoint, False to discard it and
    start over. Non-interactive callers always resume -- silently discarding
    prior progress is a worse default than continuing it, and there's no
    terminal to ask.
    """
    if not interactive:
        return True

    print(f"\n  📂 체크포인트 발견")
    print("  [1] 이어서 진행")
    print("  [2] 처음부터 시작")
    choice = input("  선택: ").strip()
    return choice != "2"


def _load_previous_summaries(root_path: str, selected: list[str]) -> dict[str, str]:
    """{relative key: summary} for files in `selected` whose content hash
    matches the last successful pack's manifest, at the conventional
    RESULT_DIR path save_aif() writes to by default (<name>.json +
    <name>.cache.json). This is what pack() checks before spending an LLM
    call on a file's summary again.

    Returns {} on any cache miss -- no previous pack there, or its output
    files are missing/unreadable/corrupt -- rather than raising. A miss just
    means every file gets summarized fresh, same as before this existed.
    """
    name = Path(root_path).name
    aif_path = RESULT_DIR / f"{name}.json"
    cache_path = RESULT_DIR / f"{name}.cache.json"
    if not aif_path.exists() or not cache_path.exists():
        return {}

    try:
        with open(aif_path, "r", encoding="utf-8") as f:
            previous_files = json.load(f).get("files", {})
        with open(cache_path, "r", encoding="utf-8") as f:
            previous_manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    report = check_freshness(selected, root_path, previous_manifest)
    return {
        rel: previous_files[rel]["summary"]
        for rel in report.unchanged
        if rel in previous_files and previous_files[rel].get("summary")
    }


def _request_summary(file_path: str, data: dict) -> str:
    """Tries once to get one file's summary; returns an empty string on failure.

    (Network retries are already handled inside llm.generate(), so this only
    tries once — whether to involve the user is up to the caller.)
    """
    if data["signatures"] or data["dependencies"]:
        response = analyze_file_summary(
            file_path,
            data["signatures"],
            data["dependencies"]
        )
    else:
        # Use the already-computed compressed text, not a fresh raw read: it's
        # cheaper (no second read, no separate truncation logic) and keeps the
        # summary grounded in what actually ships in aif.json rather than text
        # that may get stripped out of `compressed`.
        response = analyze_text_summary(file_path, data.get("compressed", ""))

    try:
        return json.loads(response).get("summary", "")
    except json.JSONDecodeError:
        return ""


def _chunked(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _request_batch_summaries(batch: list[tuple[str, dict]]) -> dict[str, str]:
    """batch: [(relative name, data), ...]. Tries one LLM call covering the
    whole batch; any name the response doesn't cover (missing entirely, or
    the model didn't echo the exact key) falls back to _request_summary()
    individually -- so a partially wrong/incomplete batch response only
    costs what it actually failed on, not the whole batch, and a fully
    garbled response degrades to the old one-call-per-file behavior instead
    of losing every file in it.
    """
    items = [
        {
            "file": name,
            "signatures": data["signatures"],
            "dependencies": data["dependencies"],
            "content": data.get("compressed", ""),
        }
        for name, data in batch
    ]
    response = analyze_batch_summaries(items)
    try:
        summaries = json.loads(response).get("summaries", {})
    except json.JSONDecodeError:
        summaries = {}

    result = {}
    for name, data in batch:
        result[name] = summaries.get(name) or _request_summary(name, data)
    return result


def _current_aif_snapshot(root: Path, files_data: dict, rules: list = None, prompt: str = "") -> dict:
    return {
        "project": {"name": root.name, "prompt": prompt},
        "rules": rules or [],
        "files_data": {
            _rel_key(fp, root): d
            for fp, d in files_data.items()
        }
    }


def pack(
    root_path: str,
    auto: bool = False,
    interactive: bool = True,
    use_cache: bool = True,
    preselected: list[str] | None = None,
    include: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict:
    """include/ignore are extra glob patterns (gitignore syntax -- see
    collect_files()'s own docstring for exactly how each is applied),
    unioned with whatever's already in the target project's .ziplex.json
    (config.py) rather than replacing it -- typically sourced from a CLI
    --include/--ignore flag for a one-off scope without editing the config
    file. Both apply before file selection (auto/preselected/interactive
    picker all choose from the same already-filtered candidate set), so a
    file excluded here never reaches the security scan or shows up as a
    choice at all, the same as one excluded by DEFAULT_IGNORE/.gitignore.

    auto controls file selection (skip the interactive picker, include all
    safe files); interactive controls whether a failing LLM call can prompt
    for input at all. The two are independent: `--auto` alone still lets
    handle_llm_failure() ask what to do on a repeated failure, while
    interactive=False makes that automatic (checkpoint + return {}) even with
    file selection left interactive. `cli.py`'s `--auto-correct` sets both
    this and whether corrector.py's interactive review runs afterward, since
    both boil down to the same question: is there a terminal to prompt?

    preselected, when given, wins over both auto and the interactive
    select_files() picker: a list of relative names (the same keys aif.json
    ends up keyed by) to include, already decided by the caller. This is
    gui_server.py's seam -- pack_service.py's file-selection screen runs
    collect_files()/scan_files() itself to show a human the safe/dangerous
    split in the browser, then passes back what they checked, since
    select_files()'s input()-based picker has no terminal to read from over
    HTTP. An empty list is valid input (selects nothing, same as an empty
    picker response) and not the same as None (which falls through to
    auto/select_files()).

    use_cache controls incremental reuse (staleness stage 2): when a
    previous successful pack is found at the conventional RESULT_DIR path
    for this project, any file whose content hash still matches gets its
    summary reused instead of spending another LLM call on it. Only summary
    is reused -- signatures/dependencies/api/compressed are always
    freshly extracted, so a human's prior manual reparenting
    (corrector.py's move_file()) never silently gets skipped along with an
    unchanged file's dependency data; a fresh pack always rebuilds
    `relationships` from scratch regardless of this flag, same as before
    incremental reuse existed.
    """
    root = Path(root_path)

    # auto-detect a checkpoint
    checkpoint = load_checkpoint(root_path)
    if checkpoint and not _resume_checkpoint_choice(interactive):
        checkpoint = None
        delete_checkpoint(root_path)

    # restore from checkpoint
    restored_rules = checkpoint.get("rules", []) if checkpoint else []
    restored_prompt = checkpoint.get("project", {}).get("prompt", "") if checkpoint else ""

    # 1. Collect files
    print("\n📁 파일 수집 중...")
    files = collect_files(root_path, **collection_kwargs(root_path, extra_include=include, extra_ignore=ignore))

    # 2. Security scan
    print("🔒 보안 스캔 중...")
    scan_result = scan_files(files)
    safe_files = scan_result["safe"]

    if scan_result["dangerous"]:
        print(f"  ⚠️  민감 파일 제외: {len(scan_result['dangerous'])}개")
        for f in scan_result["dangerous"]:
            print(f"  ❌ {Path(f).name}")

    # 3. Select files
    if preselected is not None:
        wanted = set(preselected)
        selected = [f for f in safe_files if _rel_key(f, root) in wanted]
        print(f"  ✅ {len(selected)}개 파일 선택됨 (지정된 목록 기준)")
    elif auto:
        selected = safe_files
        print(f"  ✅ 전체 {len(selected)}개 파일 선택됨")
    else:
        selected = select_files(safe_files, root_path)

    if not selected:
        print("선택된 파일 없음.")
        return {}

    # incremental reuse (staleness stage 2): {relative key: summary} for
    # files whose content hasn't changed since the last successful pack
    previous_summaries = _load_previous_summaries(root_path, selected) if use_cache else {}
    if previous_summaries:
        print(f"  ♻️  이전 pack에서 변경 없는 파일 {len(previous_summaries)}개 발견 — 요약 재사용")

    # 4. Tree-sitter analysis
    print("\n🔍 코드 구조 분석 중...")
    files_data = {}
    signatures_map = {}

    for file_path in selected:
        name = _rel_key(file_path, root)

        # restore from checkpoint
        if checkpoint and name in checkpoint.get("files_data", {}):
            print(f"  ✅ {name} (체크포인트에서 복원)")
            files_data[file_path] = checkpoint["files_data"][name]
            if files_data[file_path].get("signatures"):
                signatures_map[file_path] = files_data[file_path]["signatures"]
            continue

        sigs = extract_signatures(file_path)
        deps = extract_dependencies(file_path)
        apis = extract_api(file_path)
        compressed = compress_file(file_path)
        reused_summary = previous_summaries.get(name, "")

        files_data[file_path] = {
            "signatures": sigs,
            "dependencies": deps,
            "api": apis,
            "compressed": compressed,
            "summary": reused_summary
        }

        if sigs or deps:
            signatures_map[file_path] = sigs

        if reused_summary:
            print(f"  ♻️  {name} (변경 없음, 이전 요약 재사용)")
        else:
            print(f"  ✅ {name}")

    # 5. LLM analysis
    # Each file's summary is human-reviewed/corrected in correct_aif() later
    # (triaged by confidence -- see below -- so review effort scales with how
    # many summaries actually look suspicious, not with project size), so
    # this skips the retry menu: try each file once in parallel and fill
    # failures with a placeholder (a wrong summary still gets fixed in the
    # next step).
    print("\n🤖 LLM 분석 중...")
    pending = {
        fp: data for fp, data in files_data.items() if not data.get("summary")
    }
    # name_to_fp lets _request_batch_summaries() work with the same short,
    # stable relative keys that show up in the LLM prompt/response, then map
    # results back to the absolute paths files_data is keyed by.
    name_to_fp = {_rel_key(fp, root): fp for fp in pending}
    batches = [
        [(name, pending[name_to_fp[name]]) for name in chunk]
        for chunk in _chunked(list(name_to_fp.keys()), BATCH_SIZE)
    ]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_request_batch_summaries, batch): batch
            for batch in batches
        }
        for future in as_completed(futures):
            for name, summary in future.result().items():
                fp = name_to_fp[name]
                files_data[fp]["summary"] = summary or "요약 생성 실패"
                print(f"  ✅ {name}")

    # Confidence signal for every summary (reused, checkpoint-restored, or
    # freshly generated) -- free, no LLM call: just how much of the file's
    # own signature vocabulary shows up in its summary. correct_aif() uses
    # this to decide which summaries are worth prompting a human about.
    for data in files_data.values():
        data["confidence"] = estimate_confidence(data["summary"], data["signatures"])

    # extract rules (restored from checkpoint if available)
    rules = restored_rules
    if not rules:
        print("  📋 코딩 룰 추출 중...")
        while not rules:
            rules_response = analyze_rules(signatures_map)
            try:
                rules_data = json.loads(rules_response)
                rules = rules_data.get("rules", [])
            except json.JSONDecodeError:
                rules = []

            if not rules:
                result = handle_llm_failure(
                    "rules", "코딩 룰",
                    _current_aif_snapshot(root, files_data),
                    root_path,
                    interactive=interactive,
                )
                if result == "EXIT":
                    return {}
                elif result is None:
                    continue
                else:
                    rules = [r.strip() for r in result.split(",")]
    else:
        print("  📋 코딩 룰 (체크포인트에서 복원)")

    # generate prompt (restored from checkpoint if available)
    prompt = restored_prompt
    if not prompt:
        print("  ✍️  AI 가이드 생성 중...")
        while not prompt:
            prompt_response = analyze_prompt(
                project_name=root.name,
                architecture=[],
                rules=rules
            )
            try:
                prompt_data = json.loads(prompt_response)
                prompt = prompt_data.get("prompt", "")
            except json.JSONDecodeError:
                prompt = ""

            if not prompt:
                result = handle_llm_failure(
                    "prompt", "AI 가이드",
                    _current_aif_snapshot(root, files_data, rules),
                    root_path,
                    interactive=interactive,
                )
                if result == "EXIT":
                    return {}
                elif result is None:
                    continue
                else:
                    prompt = result
    else:
        print("  ✍️  AI 가이드 (체크포인트에서 복원)")

    # 6. Token counting
    # Compares raw project text against the actual per-file aif.json payload
    # (just the summary -- signatures/dependencies/api/compressed are either
    # working state pruned later in correct_aif(), or split out to a sibling
    # detail.json by save_aif() and not part of what's loaded by default).
    # files_data is fully populated with summaries by now, so this reflects
    # the real savings an AI gets from reading aif.json.
    print("\n📊 토큰 분석 중...")
    token_results, _ = analyze_tokens_with_payload(selected, files_data)

    # 7. Assemble AIF.json
    aif = {
        "project": {
            "name": root.name,
            "prompt": prompt
        },
        "rules": rules,
        "tokens": {
            model: {
                "original": data["original"],
                "compressed": data["compressed"],
                "saved_pct": data["saved_pct"]
            }
            for model, data in token_results.items()
        },
        "files": {
            _rel_key(fp, root): {
                "summary": data["summary"],
                "confidence": data["confidence"],
                "signatures": data["signatures"],
                "dependencies": data["dependencies"],
                "api": data["api"],
                "compressed": data["compressed"]
            }
            for fp, data in files_data.items()
        },
        # Working state, not part of the shipped aif.json: a {file: content
        # hash} snapshot of exactly what was packed, so a later
        # freshness.check_freshness() call can tell whether this output has
        # drifted from the files on disk without re-running any of the above.
        # save_aif() pulls this out into a sibling <name>.cache.json, the
        # same way it pulls `compressed` out into <name>.detail.json.
        "_manifest": build_manifest(selected, root_path),
    }

    # delete the checkpoint on success
    delete_checkpoint(root_path)

    return aif


def save_aif(aif: dict, output_path: str | None = None) -> None:
    """Writes the AIF result to output_path, or to result/<project name>.json if
    output_path isn't given — mirroring CHECKPOINT_DIR, anchored to the repo root
    rather than the caller's cwd, so `pack` writes to the same place regardless of
    where it's invoked from.

    Splits two things out of `aif` into sibling files, keyed the same way as
    `files`:
    - `compressed` -> "<name>.detail.json". aif.json (summary + relationships)
      is what an AI reads by default -- for a file with no compressed body to
      strip (README, config, lang files, ...) `compressed` is close to the raw
      original, so shipping it unconditionally on every file undoes the token
      savings for exactly the files that benefit least from it. mcp_server.py's
      get_detail tool is what actually fetches detail.json today, only for
      files an AI decides it needs.
    - `_manifest` -> "<name>.cache.json" (flat, not per-file). A {file: content
      hash} snapshot of what was packed, for freshness.check_freshness() to
      compare against later -- not part of aif.json itself, since it's
      packaging-internal bookkeeping an AI reading the project has no use for.
    """
    if output_path is None:
        RESULT_DIR.mkdir(exist_ok=True)
        output_path = RESULT_DIR / f"{aif['project']['name']}.json"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = aif.get("_manifest")

    lean_files = {}
    detail = {}
    for name, data in aif["files"].items():
        lean_files[name] = {k: v for k, v in data.items() if k != "compressed"}
        detail[name] = {"compressed": data.get("compressed", "")}

    lean_aif = {k: v for k, v in aif.items() if k != "_manifest"}
    lean_aif["files"] = lean_files

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(lean_aif, f, ensure_ascii=False, indent=2)
    print(f"\n✅ AIF.json 저장됨: {output_path}")

    detail_path = output_path.with_name(f"{output_path.stem}.detail.json")
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(detail, f, ensure_ascii=False, indent=2)
    print(f"📦 상세 정보(compressed) 저장됨: {detail_path}")

    if manifest is not None:
        cache_path = output_path.with_name(f"{output_path.stem}.cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"🗂️  캐시(해시) 저장됨: {cache_path}")