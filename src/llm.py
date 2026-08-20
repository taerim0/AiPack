import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()


def _clean_json(text: str) -> str:
    # 마크다운 코드블록 제거
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    return text.strip()


class GeminiProvider:
    """Gemini REST API 프로바이더.

    다른 LLM을 추가하려면 이 클래스처럼 generate(prompt, retry) -> str 만
    구현해서 아래 PROVIDERS에 한 줄 등록하면 된다. analyze_* 함수들은
    provider가 뭐든 상관없이 모듈 레벨 generate()만 호출한다.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-flash-latest"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={self.api_key}"
        )

    def generate(self, prompt: str, retry: int = 5) -> str:
        for attempt in range(retry):
            response = requests.post(self.url, json={
                "contents": [{"parts": [{"text": prompt}]}]
            })
            data = response.json()

            if "candidates" in data:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return _clean_json(text)

            error_code = data.get("error", {}).get("code", 0)
            error_msg = data.get("error", {}).get("message", "unknown")

            if error_code in [503, 429]:
                wait = 5 * (attempt + 1)  # 5초, 10초, 15초
                print(f"  ⚠️  서버 과부하, {wait}초 후 재시도 ({attempt+1}/{retry})")
                time.sleep(wait)
                continue

            print(f"  ❌ API 에러: {error_msg}")
            break

        return "{}"


# 지원 프로바이더 레지스트리. 새 LLM을 추가하려면 여기에 클래스 하나 더하고
# LLM_PROVIDER 환경변수로 고르게 하면 된다 (예: PROVIDERS["claude"] = ClaudeProvider).
PROVIDERS = {
    "gemini": GeminiProvider,
}

_provider = PROVIDERS[os.getenv("LLM_PROVIDER", "gemini")]()


def generate(prompt: str, retry: int = 5) -> str:
    """현재 활성 LLM 프로바이더에 위임. 스레드 세이프 (provider별 상태는 읽기 전용)."""
    return _provider.generate(prompt, retry=retry)


def analyze_file_summary(file_path: str, signatures: list[str], dependencies: list[str]) -> str:
    prompt = f"""
Based on the file info below, summarize this file's role in one line.
Respond with JSON only, nothing else.

File: {file_path}
Function signatures: {signatures}
Dependencies: {dependencies}

{{"summary": "..."}}
"""
    return generate(prompt)


def analyze_text_summary(file_path: str, content: str) -> str:
    prompt = f"""
Based on the file content below, summarize this file's role in one line.
Respond with JSON only, nothing else.

File: {file_path}
Content:
{content[:500]}

{{"summary": "..."}}
"""
    return generate(prompt)


def analyze_rules(signatures_map: dict) -> str:
    prompt = f"""
Analyze the function signature patterns of the project below
and extract its implicit coding rules.
Respond with JSON only, nothing else.

Signature list: {signatures_map}

{{"rules": ["...", "...", "..."]}}
"""
    return generate(prompt)


def analyze_prompt(project_name: str, architecture: list[str], rules: list[str]) -> str:
    prompt = f"""
Based on the project info below, write 2-3 sentences of core context
that let an AI understand this project immediately on first look.
Respond with JSON only, nothing else.

Project name: {project_name}
Architecture: {architecture}
Coding rules: {rules}

{{"prompt": "..."}}
"""
    return generate(prompt)

def analyze_relationships(file_summaries: dict) -> str:
    prompt = f"""
Based on the file names and partial content below,
extract only the direct dependency relationships between files.

Rules:
- Include only cases where one file directly references or uses another
- Exclude cases that are merely related in topic
- Use an empty array if there is no relationship

Respond with JSON only, nothing else.

File list:
{file_summaries}

{{
  "relationships": {{
    "fileA": ["fileB it directly references"],
    "fileB": []
  }}
}}
"""
    return generate(prompt)
