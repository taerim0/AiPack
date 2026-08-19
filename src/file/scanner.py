import subprocess
import json
import re

# Secretlint 실패 시 fallback용 패턴
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
        return None  # Secretlint 실패 → fallback


def _scan_with_pattern(file_path: str) -> bool:
    try:
        content = open(file_path, "r", encoding="utf-8").read()
    except (UnicodeDecodeError, IsADirectoryError):
        return False

    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False


def scan_file(file_path: str) -> bool:
    # 1. Secretlint 시도
    result = _scan_with_secretlint(file_path)

    # 2. Secretlint 실패 시 패턴 기반 fallback
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