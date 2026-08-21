import json
from pathlib import Path

from file.collector import collect_files
from file.scanner import scan_files
from file.selector import select_files
from file.textutil import relative_key as _rel_key
from extract.code.extractor import extract_signatures, extract_dependencies, extract_api
from extract.code.compressor import compress_file
from text_references import find_text_references_for_file
from tokenizer import analyze_tokens_with_payload
from llm import analyze_rules, analyze_prompt
from freshness import build_manifest, load_previous_summaries
from confidence import estimate_confidence
from config import collection_kwargs
from tech_stack import detect_tech_stack
import checkpoint as ckpt
import summarizer

RESULT_DIR = Path(__file__).parent.parent / "result"


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
    checkpoint.handle_llm_failure() ask what to do on a repeated failure,
    while interactive=False makes that automatic (checkpoint + return {})
    even with file selection left interactive. `cli.py`'s `--auto-correct`
    sets both this and whether corrector.py's interactive review runs
    afterward, since both boil down to the same question: is there a
    terminal to prompt?

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
    checkpoint = ckpt.load_checkpoint(root_path)
    if checkpoint and not ckpt.resume_checkpoint_choice(interactive):
        checkpoint = None
        ckpt.delete_checkpoint(root_path)

    # restore from checkpoint
    restored_rules, restored_prompt, restored_files_data = ckpt.unpack_snapshot(checkpoint)

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
    previous_summaries = load_previous_summaries(root_path, selected, RESULT_DIR) if use_cache else {}
    if previous_summaries:
        print(f"  ♻️  이전 pack에서 변경 없는 파일 {len(previous_summaries)}개 발견 — 요약 재사용")

    # 4. Tree-sitter analysis
    print("\n🔍 코드 구조 분석 중...")
    files_data = {}
    signatures_map = {}

    # All selected files' relative keys, computed once -- text_references.
    # find_text_references_for_file() needs the real candidate list to
    # match a non-code file's content against, not just file_path itself.
    all_names = [_rel_key(fp, root) for fp in selected]

    # Text-reference matches (see text_references.py), kept separate from
    # files_data[fp]["dependencies"] until *after* step 5's LLM summary
    # loop below, not merged in here -- summarizer.request_summary()/
    # analyze_batch_summaries() both switch a file's summary prompt from
    # content-based to signature/dependency-based the moment `dependencies`
    # is non-empty. Merging immediately would silently swap a text file's
    # (README, .tscn, ...) content-based prompt for a signatures=[]/
    # dependencies=[the very refs just found]-only one the instant it
    # picked up any text reference -- Gemini would summarize it having
    # never seen its actual content. Computed for every file regardless of
    # checkpoint-restore, so a run resumed mid-way still gets it.
    text_refs_by_path: dict[str, list[str]] = {}

    for file_path in selected:
        name = _rel_key(file_path, root)
        text_refs_by_path[file_path] = find_text_references_for_file(file_path, name, all_names)

        # restore from checkpoint
        if name in restored_files_data:
            print(f"  ✅ {name} (체크포인트에서 복원)")
            files_data[file_path] = restored_files_data[name]
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
    # this skips the retry menu: try each file once in parallel (see
    # summarizer.generate_summaries) and fill failures with a placeholder (a
    # wrong summary still gets fixed in the next step).
    print("\n🤖 LLM 분석 중...")
    pending = {
        fp: data for fp, data in files_data.items() if not data.get("summary")
    }
    for fp, summary in summarizer.generate_summaries(pending, root).items():
        files_data[fp]["summary"] = summary

    # Only now -- after every summary prompt has already been built from
    # code-only `dependencies` above -- fold in the free text-reference
    # matches computed earlier. `relationships` (built later, from this
    # same `dependencies` field) is meant to include them; the LLM summary
    # step just needed to not see them yet. See text_refs_by_path's own
    # comment above for why the ordering matters.
    for fp, data in files_data.items():
        if text_refs_by_path.get(fp):
            data["dependencies"] = data["dependencies"] + text_refs_by_path[fp]

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
                result = ckpt.handle_llm_failure(
                    "rules", "코딩 룰",
                    ckpt.build_snapshot(root, files_data),
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
                result = ckpt.handle_llm_failure(
                    "prompt", "AI 가이드",
                    ckpt.build_snapshot(root, files_data, rules),
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
            "prompt": prompt,
            # Free (no LLM call), manifest-based fact block -- see
            # tech_stack.py's own docstring for why this exists alongside
            # `rules` rather than folding into it.
            "tech_stack": detect_tech_stack(root_path),
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
    ckpt.delete_checkpoint(root_path)

    return aif


def save_aif(aif: dict, output_path: str | None = None) -> None:
    """Writes the AIF result to output_path, or to result/<project name>.json if
    output_path isn't given — mirroring checkpoint.CHECKPOINT_DIR, anchored to
    the repo root rather than the caller's cwd, so `pack` writes to the same
    place regardless of where it's invoked from.

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
