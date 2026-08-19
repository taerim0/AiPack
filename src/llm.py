import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={API_KEY}"

def clean_json(text: str) -> str:
    # 마크다운 코드블록 제거
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    return text.strip()


def generate(prompt: str, retry: int = 5) -> str:  # 3 → 5
    for attempt in range(retry):
        response = requests.post(URL, json={
            "contents": [{"parts": [{"text": prompt}]}]
        })
        data = response.json()

        if "candidates" in data:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return clean_json(text)

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