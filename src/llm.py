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
아래 파일 정보를 보고 이 파일의 역할을 한 줄로 요약해줘.
JSON으로만 답해. 다른 말 하지 마.

파일명: {file_path}
함수 시그니처: {signatures}
의존성: {dependencies}

{{"summary": "..."}}
"""
    return generate(prompt)


def analyze_text_summary(file_path: str, content: str) -> str:
    prompt = f"""
아래 파일 내용을 보고 이 파일의 역할을 한 줄로 요약해줘.
JSON으로만 답해. 다른 말 하지 마.

파일명: {file_path}
내용:
{content[:500]}

{{"summary": "..."}}
"""
    return generate(prompt)


def analyze_rules(signatures_map: dict) -> str:
    prompt = f"""
아래 프로젝트의 함수 시그니처 패턴을 분석해서
암묵적인 코딩 룰을 추출해줘.
JSON으로만 답해. 다른 말 하지 마.

시그니처 목록: {signatures_map}

{{"rules": ["...", "...", "..."]}}
"""
    return generate(prompt)


def analyze_prompt(project_name: str, architecture: list[str], rules: list[str]) -> str:
    prompt = f"""
아래 프로젝트 정보를 보고
AI가 이 프로젝트를 처음 봤을 때 바로 이해할 수 있도록
핵심 컨텍스트를 2-3문장으로 만들어줘.
JSON으로만 답해. 다른 말 하지 마.

프로젝트명: {project_name}
아키텍처: {architecture}
코딩 룰: {rules}

{{"prompt": "..."}}
"""
    return generate(prompt)

def analyze_relationships(file_summaries: dict) -> str:
    prompt = f"""
아래 파일들의 이름과 내용 일부를 보고
파일 간의 직접적인 의존 관계만 추출해줘.

규칙:
- 한 파일이 다른 파일을 직접 참조하거나 사용하는 경우만 포함
- 단순히 주제가 비슷한 경우는 제외
- 관계가 없으면 빈 배열

JSON으로만 답해. 다른 말 하지 마.

파일 목록:
{file_summaries}

{{
  "relationships": {{
    "파일A": ["직접 참조하는 파일B"],
    "파일B": []
  }}
}}
"""
    return generate(prompt)
