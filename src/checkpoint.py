"""pack()'s checkpoint/resume system, split out of packager.py so that module
is left owning just the pipeline itself, not also this: saving/loading/
deleting a checkpoint file, deciding what to do when an LLM call has
exhausted its own retries (retry / answer manually / checkpoint and exit),
and the same question for a checkpoint found at the start of a run (resume
it / discard it and start over).

Every function here takes an `interactive` flag rather than calling
input()/print() unconditionally, so a non-interactive `pack` (CI, scripted
use, `--auto-correct`) degrades to a safe default -- checkpoint-and-exit for
a failing LLM call, always-resume for a found checkpoint -- instead of
EOFError-ing against closed stdin.
"""

import json
from pathlib import Path

from file.textutil import relative_key as _rel_key

CHECKPOINT_DIR = Path(__file__).parent.parent / "checkpoint"


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


def build_snapshot(root: Path, files_data: dict, rules: list = None, prompt: str = "") -> dict:
    """The shape handle_llm_failure() checkpoints on a failure -- everything
    pack() has produced so far, keyed by relative name (matching what
    unpack_snapshot() below expects to restore from), so a resumed run can
    skip straight past whatever already succeeded.
    """
    return {
        "project": {"name": root.name, "prompt": prompt},
        "rules": rules or [],
        "files_data": {
            _rel_key(fp, root): d
            for fp, d in files_data.items()
        }
    }


def unpack_snapshot(checkpoint: dict | None) -> tuple[list, str, dict]:
    """The read-side counterpart to build_snapshot() -- pulls (rules, prompt,
    files_data) back out of a loaded checkpoint, so a caller restoring from
    one never has to know this shape's exact keys itself. Keeps the shape
    defined in exactly one place: a future change to build_snapshot()'s keys
    has to change this function right alongside it, in the same file,
    instead of silently drifting from a raw dict-indexing read site
    somewhere else that build_snapshot() has no visibility into.

    checkpoint=None (nothing to resume, e.g. load_checkpoint() found
    nothing) returns the same empty defaults an absent checkpoint already
    implied before this function existed.
    """
    if not checkpoint:
        return [], "", {}
    rules = checkpoint.get("rules", [])
    prompt = checkpoint.get("project", {}).get("prompt", "")
    files_data = checkpoint.get("files_data", {})
    return rules, prompt, files_data


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


def resume_checkpoint_choice(interactive: bool) -> bool:
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
