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


def generate(prompt: str, retry: int = 3) -> str:
    for attempt in range(retry):
        response = requests.post(URL, json={
            "contents": [{"parts": [{"text": prompt}]}]
        })
        data = response.json()

        if "candidates" in data:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return clean_json(text)

        error_code = data.get("error", {}).get("code", 0)

        if error_code == 503:
            wait = 2 ** attempt
            print(f"  ⚠️  API 혼잡, {wait}초 후 재시도 ({attempt+1}/{retry})")
            time.sleep(wait)
            continue

        print(f"  ❌ API 에러: {data.get('error', {}).get('message', 'unknown')}")
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