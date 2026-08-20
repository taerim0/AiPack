import os
import time
from typing import Protocol

import requests
from dotenv import load_dotenv

load_dotenv()


def _clean_json(text: str) -> str:
    # strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)
    return text.strip()


class LLMProvider(Protocol):
    """The contract every provider must satisfy to be usable via generate().

    Structural (Protocol), not a base class to inherit from: a provider just
    needs a matching generate() method, nothing registers or declares
    conformance. Kept minimal on purpose -- when a second provider actually
    gets added, this is the seam to grow (e.g. auth/config passed through
    __init__ can differ freely per provider; only generate()'s shape matters
    here) and the natural point to split providers into their own module
    (or package, if there end up being several) instead of stacking classes
    with very different error-handling/retry logic into this one file.
    """

    def generate(self, prompt: str, retry: int = 5) -> str: ...


class GeminiProvider:
    """Gemini REST API provider.

    To add another LLM, implement generate(prompt, retry) -> str like this
    class (see LLMProvider above) and register it in PROVIDERS below with one
    line. The analyze_* functions only ever call the module-level generate(),
    regardless of which provider is active.
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
                wait = 5 * (attempt + 1)  # 5s, 10s, 15s, ...
                print(f"  ⚠️  서버 과부하, {wait}초 후 재시도 ({attempt+1}/{retry})")
                time.sleep(wait)
                continue

            print(f"  ❌ API 에러: {error_msg}")
            break

        return "{}"


# Registry of supported providers. To add a new LLM, add a class here and let
# LLM_PROVIDER select it (e.g. PROVIDERS["claude"] = ClaudeProvider).
PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
}

_provider: LLMProvider = PROVIDERS[os.getenv("LLM_PROVIDER", "gemini")]()


def generate(prompt: str, retry: int = 5) -> str:
    """Delegates to the currently active LLM provider. Thread-safe (provider state is read-only)."""
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
