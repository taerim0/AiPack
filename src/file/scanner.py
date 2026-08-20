import subprocess
import json
import re

from file.textutil import read_text

# fallback patterns used when secretlint fails/isn't available
SENSITIVE_PATTERNS = [
    r'AWS_SECRET\s*=\s*["\']',
    r'API_KEY\s*=\s*["\']',
    r'PASSWORD\s*=\s*["\']',
    r'SECRET_KEY\s*=\s*["\']',
    r'PRIVATE_KEY\s*=\s*["\']',
    r'ACCESS_TOKEN\s*=\s*["\']',
    r'DATABASE_URL\s*=\s*["\']',
]

def _scan_with_secretlint(file_path: str) -> bool:
    try:
        result = subprocess.run(
            ["secretlint", "--format", "json", file_path],
            capture_output=True,
            text=True
        )
        findings = json.loads(result.stdout)
        return len(findings["messages"]) > 0
    except (json.JSONDecodeError, KeyError, FileNotFoundError):
        return None  # secretlint failed -> fallback


def _scan_with_pattern(file_path: str) -> bool:
    content = read_text(file_path)
    if content is None:
        return False

    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


def scan_file(file_path: str) -> bool:
    # 1. try secretlint
    result = _scan_with_secretlint(file_path)

    # 2. pattern-based fallback if secretlint failed
    if result is None:
        return _scan_with_pattern(file_path)

    return result


def scan_files(file_paths: list[str]) -> dict:
    results = {"safe": [], "dangerous": []}
    for file_path in file_paths:
        if scan_file(file_path):
            results["dangerous"].append(file_path)
        else:
            results["safe"].append(file_path)
    return results