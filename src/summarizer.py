"""Per-file summary generation for pack(), split out of packager.py so that
module is left owning just the pipeline itself, not also this: batching
pending files into fewer, larger LLM requests (see llm.analyze_batch_
summaries), and falling back to a per-file request for anything a batch
response didn't cover.

generate_summaries() is the entry point pack() actually calls; the smaller
functions below it (chunked/request_summary/request_batch_summaries) are
exposed too, both because pack() doesn't need the batching/threading detail
and because tests exercise them directly without spinning up a whole pack()
run.

Reusing a previous pack's summary for an unchanged file (staleness stage 2)
is deliberately *not* here -- that's freshness.load_previous_summaries(),
since deciding what still counts as "fresh" is squarely that module's own
subject, not a concern of the LLM-call batching this module actually owns.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json

from file.textutil import relative_key as _rel_key
from llm import analyze_file_summary, analyze_text_summary, analyze_batch_summaries

# Concurrency used when requesting per-file summaries in parallel.
# Kept conservative with LLM API rate limits in mind — adjust if needed.
MAX_WORKERS = 4

# Files per batched summary request (see llm.analyze_batch_summaries). Trades
# a somewhat larger prompt for far fewer requests -- directly eases the
# rate-limit pressure that drives most first-pack retries, without changing
# MAX_WORKERS' cross-batch parallelism.
BATCH_SIZE = 8


def request_summary(file_path: str, data: dict) -> str:
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


def chunked(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def request_batch_summaries(batch: list[tuple[str, dict]]) -> dict[str, str]:
    """batch: [(relative name, data), ...]. Tries one LLM call covering the
    whole batch; any name the response doesn't cover (missing entirely, or
    the model didn't echo the exact key) falls back to request_summary()
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
        result[name] = summaries.get(name) or request_summary(name, data)
    return result


def generate_summaries(pending: dict[str, dict], root: Path) -> dict[str, str]:
    """Requests a summary for every entry in `pending` ({absolute file path:
    data}), batching BATCH_SIZE-at-a-time (see llm.analyze_batch_summaries)
    across a MAX_WORKERS thread pool, printing progress as each one lands.
    Returns {file path: summary} -- same keys as `pending` itself, so the
    caller can write straight back into its own files_data dict.

    Each summary falls back to a placeholder ("요약 생성 실패") rather than
    an empty string on failure: correct_aif()'s per-file review (triaged by
    confidence.py) is what catches and fixes a wrong or missing summary
    later, not a retry loop here -- see pack()'s own docstring for why that
    trade-off (try once, in parallel, let review catch the rest) was made.
    """
    name_to_fp = {_rel_key(fp, root): fp for fp in pending}
    batches = [
        [(name, pending[name_to_fp[name]]) for name in chunk]
        for chunk in chunked(list(name_to_fp.keys()), BATCH_SIZE)
    ]

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(request_batch_summaries, batch): batch
            for batch in batches
        }
        for future in as_completed(futures):
            for name, summary in future.result().items():
                fp = name_to_fp[name]
                results[fp] = summary or "요약 생성 실패"
                print(f"  ✅ {name}")
    return results
