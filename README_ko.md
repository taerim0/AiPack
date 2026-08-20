# Ziplex

[English](README.md) | **한국어**

**로컬 프로젝트를 AI가 즉시 읽어들일 수 있는 컨텍스트 파일로 변환합니다 — 수백 개의 원본 파일을 일일이 넘겨줄 필요 없이.**

Ziplex는 프로젝트를 순회하며 Tree-sitter로 압축·구조화하고, LLM으로 요약한 뒤, 사람이 결과를 검토·수정하고 나서야 최종 결과물을 내보냅니다. 결과물은 `aif.json` — 작고 구조화된 "AI 컨텍스트 포맷" 파일입니다.

> ⚠️ 활발히 개발 중입니다. 인터페이스와 출력 포맷은 아직 바뀔 수 있습니다.

---

## How it works

```
project/  ──►  수집  ──►  보안 스캔  ──►  선택  ──►  파싱 & 추출
                                                          │
          aif.json  ◄──  사람 보정  ◄──  LLM 요약  ◄──────┘
        + detail.json
```

1. **수집** — `node_modules/`, 빌드 캐시(`.gradle/`, `target/`, `.pytest_cache/` 등), 그리고 프로젝트 자체의 `.gitignore`가 제외하는 대상을 건너뛰며 프로젝트를 순회합니다. 텍스트로 디코딩할 수 없는 파일(이미지, 바이너리, 컴파일된 산출물)도 함께 제외됩니다 — 모든 바이너리 포맷을 이름 패턴으로 나열할 수는 없으므로, 파일명으로 추측하는 대신 직접 확인합니다.
2. **보안 스캔** — 남은 모든 파일에서 민감 정보(API 키, 비밀번호, 토큰)를 `secretlint`로 검사하고, 설치돼 있지 않으면 정규식 기반 폴백을 사용합니다. 걸린 파일은 파이프라인에 아예 들어오지 않습니다.
3. **선택** — 포함할 파일을 대화형으로 고르거나, `--auto`로 안전한 파일 전체를 바로 선택합니다.
4. **파싱 & 추출** — Tree-sitter가 지원 언어의 소스 파일을 파싱해 함수 시그니처, import, (데코레이터 기반 라우트의 경우) API 엔드포인트를 뽑아냅니다.
5. **압축** — 함수 본문을 마커 하나로 치환해 구조는 유지하면서 토큰을 줄입니다. 코드가 아닌 텍스트(JSON, Markdown, 일반 텍스트)도 자체 압축 과정을 거치며, Markdown 코드 블록은 감지된 언어를 기준으로 코드 압축기를 그대로 재사용합니다.
6. **요약** — Gemini가 파일별 한 줄 요약과, 수집된 시그니처로부터 추론한 프로젝트 전체 코딩 룰, 그리고 AI를 위한 프로젝트 가이드를 생성합니다.
7. **보정** — 사람이 프로젝트 이름, 가이드, 룰, 모든 파일 요약을 검토·수정하고, 최종 관계 그래프가 만들어지기 전에 의존성 트리에서 파일을 직접 재배치(순환 참조 감지 포함)할 수도 있습니다.
8. **패키징** — 즉시 로드할 수 있는 가벼운 `aif.json`(요약 + 관계 정보)을 저장하고, 압축된 코드 본문처럼 더 무거운 데이터는 별도의 `detail.json`으로 분리해 모든 파일에 기본으로 딸려가지 않고 필요할 때만 쓰도록 남겨둡니다.

## Features

- **다국어 코드 압축** — 현재 Python, Java, TypeScript, JavaScript를 지원하며, 언어별 설정 테이블(`LanguageConfig`)로 관리되어 새 문법 추가가 전체 재작성이 아니라 항목 하나 추가로 끝납니다.
- **코드 외 텍스트 압축** — JSON과 Markdown(내부 코드 펜스 포함), 일반 텍스트 전용 압축기를 코드 압축기와 같은 "본문 보존" 철학으로 제공합니다.
- **내장 보안 스캔** — `secretlint`를 우선 사용하고 정규식 폴백을 갖춰, 민감한 파일이 수집 단계를 통과하지 못하게 합니다.
- **Human-in-the-loop 보정** — LLM이 만든 모든 결과물(요약, 룰, 프로젝트 가이드, 의존성 트리)을 저장 전에 검토·수정할 수 있습니다.
- **정직한 토큰 계산** — GPT-4o, GPT-3.5, GPT-4 인코딩 기준으로 `tiktoken`을 이용해 전/후 토큰을 비교하며, 단순 압축률이 아니라 실제로 `aif.json`에 실리는 내용을 기준으로 계산합니다.
- **가벼운 출력 + 필요할 때 상세 정보** — `aif.json`은 요약 + 관계 정보만 담아 작게 유지되고, 파일별 전체 압축 코드는 `detail.json`에 저장되어 향후 MCP 레이어가 생기면 필요할 때 불러올 수 있습니다.
- **LLM 불안정성에 강함** — 레이트 리밋에는 백오프를 두고 재시도하고, 실패한 실행을 처음부터 다시 하지 않고 이어서 진행할 수 있는 체크포인트 시스템을 갖췄습니다.
- **LLM 프로바이더 독립적** — Gemini를 다른 모델로 바꾸는 작업은 `generate()` 메서드 하나를 구현해 등록하는 것으로 끝나며, 나머지 파이프라인은 건드리지 않습니다.
- **git 저장소 전용이 아님** — 일반적인 소프트웨어 저장소가 아니어도, 확장자를 넘나드는 관계를 가진 로컬 파일 모음이라면 무엇이든(게임 모드, 에셋 프로젝트 등) 동작합니다.

## Quick start

```bash
venv\Scripts\activate
pip install -r requirement.txt        # 참고: 파일명에 "s"가 없습니다
```

`.env`에 `GEMINI_API_KEY=...`를 추가한 뒤:

```bash
# 전체 파이프라인: 수집, 스캔, 선택, 압축, 요약, 보정
python src/cli.py pack ./your-project/

# 대화형 파일 선택을 건너뛰고 안전한 파일 전체 포함
python src/cli.py pack ./your-project/ --auto

# 출력 경로 지정 (out.json + out.detail.json이 함께 저장됨)
python src/cli.py pack ./your-project/ -o output/out.json
```

<details>
<summary>전체 명령어</summary>

| 명령어 | 설명 |
|---|---|
| `pack <path>` | 전체 파이프라인 — 대부분 이걸 쓰면 됩니다 |
| `collect <path>` | 파일 수집 + 보안 스캔만 |
| `tokens <path>` | 압축 전/후 토큰 수 |
| `tree <path>` | 의존성 트리만 |
| `select <path>` | 대화형 파일 선택만 |
| `analyze <path>` | LLM 분석만 |
| `signatures \| dependencies \| api \| compress \| debug <file>` | 파일 하나에 대해 추출 단계 하나만 실행 |

</details>

## Output format

```jsonc
// aif.json — 작고, 처음부터 로드되는 파일
{
  "project": { "name": "...", "prompt": "..." },
  "rules": ["..."],
  "tokens": { "GPT-4o": { "original": 3100, "compressed": 749, "saved_pct": 75.8 } },
  "files": { "src/App.tsx": { "summary": "..." } },
  "relationships": { "src/App.tsx": { "internal": ["..."], "external": ["react"] } }
}
```

```jsonc
// out.detail.json — 더 무거우며, 파일을 자세히 봐야 할 때만 가져옴
{
  "src/App.tsx": { "compressed": "import React ...\n    ⋮----\nexport default App" }
}
```

## Tech stack

Python 3.11 · [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) (Python/Java/TypeScript/JavaScript 문법) · [tiktoken](https://github.com/openai/tiktoken) · Gemini API (`gemini-flash-latest`, `requests`를 통한 순수 REST 호출) · `secretlint` · `pathspec`

## Roadmap

**MCP 통합** — `aif.json`/`detail.json`을 MCP 서버로 노출해 Claude Code나 Cursor 같은 도구가 프로젝트 컨텍스트를 필요할 때마다 질의할 수 있게 합니다. 먼저 요약을 가져오고, 실제로 필요한 파일의 상세 정보만 그때그때 가져오는 방식입니다. *출력 포맷을 이미 lean/detail 구조로 나눠둔 것 자체가 이 작업을 재작성이 아니라 자연스러운 다음 단계로 만들어줍니다.*

**AI로의 선택적 파일 전달** — Ziplex에서 특정 파일을 골라 복사-붙여넣기 없이 대화에 바로 전달합니다. 파일 내용뿐 아니라 의존성, 시그니처, 요약까지 함께 실려갑니다.

**모든 파일 타입에 대한 관계 분석** — 의존성 그래프를 코드 파일 너머로 확장해, LLM 추론으로 설정·텍스트·바이너리 자산까지 하나의 그림으로 연결합니다.

**언어 지원 확대** — 게임 개발에 특화된 언어(GDScript, Lua, ZenScript)와 추가 프레임워크로 Tree-sitter 지원 범위를 넓힙니다.

## License

[MIT](LICENSE)
