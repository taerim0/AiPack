# Ziplex

[English](README.md) | **한국어**

**로컬 프로젝트를 AI가 곧바로 읽을 수 있는 컨텍스트 파일 하나로 압축합니다.** 수백 개 파일을 일일이 넘겨줄 필요가 없습니다.

Ziplex는 프로젝트 전체를 훑으면서 Tree-sitter로 압축·구조화하고, LLM으로 요약을 붙인 다음, 사람이 한 번 검토하고 나서야 결과물을 내보냅니다. 그 결과물이 `aif.json`입니다 — 작고 구조화된 "AI 컨텍스트 포맷" 파일입니다.

> ⚠️ 활발히 개발 중입니다. 인터페이스와 출력 포맷은 아직 바뀔 수 있습니다.

---

## 동작 방식

```
project/  ──►  수집  ──►  보안 스캔  ──►  선택  ──►  파싱 & 추출
                                                          │
          aif.json  ◄──  사람 보정  ◄──  LLM 요약  ◄──────┘
        + detail.json
```

1. **수집** — 프로젝트를 훑으면서 `node_modules/`, 빌드 캐시(`.gradle/`, `target/`, `.pytest_cache/` 등), 프로젝트 자체 `.gitignore`에 걸리는 파일은 건너뜁니다. 텍스트로 읽히지 않는 파일(이미지, 바이너리, 컴파일 산출물)도 제외되는데, 모든 바이너리 포맷을 이름만 보고 걸러낼 순 없으니 파일을 직접 열어서 확인합니다.
2. **보안 스캔** — 남은 파일은 전부 `secretlint`로 민감 정보(API 키, 비밀번호, 토큰)가 있는지 검사합니다. `secretlint`가 없으면 정규식 기반 검사로 대체합니다. 여기 걸린 파일은 파이프라인에 아예 들어오지 못합니다.
3. **선택** — 어떤 파일을 포함할지 직접 고를 수도 있고, `--auto` 옵션으로 안전한 파일을 한 번에 전부 선택할 수도 있습니다.
4. **파싱 & 추출** — 지원 언어의 소스 파일은 Tree-sitter로 파싱해서 함수 시그니처, import 구문, (데코레이터 기반 라우트라면) API 엔드포인트까지 뽑아냅니다.
5. **압축** — 함수 본문은 마커 하나로 치환해서 구조는 그대로 두고 토큰만 줄입니다. 코드가 아닌 텍스트(JSON, Markdown, 일반 텍스트)도 각자 방식으로 압축되고, Markdown 안의 코드 블록은 언어를 감지해서 코드 압축기를 그대로 재활용합니다.
6. **요약** — Gemini가 파일마다 한 줄 요약을 붙이고, 모아둔 시그니처에서 프로젝트 전체의 코딩 룰을 추론하고, AI를 위한 프로젝트 가이드까지 만들어냅니다.
7. **보정** — 프로젝트 이름, 가이드, 룰, 파일별 요약까지 사람이 직접 검토하고 고칠 수 있습니다. 최종 관계 그래프를 만들기 전에 의존성 트리에서 파일 위치를 직접 옮기는 것도 가능합니다(순환 참조는 자동으로 감지됩니다).
8. **패키징** — 바로 로드할 수 있는 가벼운 `aif.json`(요약 + 관계 정보)을 저장합니다. 압축된 코드 본문처럼 무거운 데이터는 `detail.json`으로 따로 빼서, 모든 파일에 기본으로 딸려가는 대신 필요할 때만 꺼내 쓰도록 남겨둡니다.

## 주요 기능

- **다국어 코드 압축** — 지금은 Python, Java, TypeScript, JavaScript를 지원합니다. 언어별 설정을 테이블(`LanguageConfig`) 하나로 관리해서, 새 문법을 추가할 때 코드를 갈아엎을 필요 없이 항목 하나만 추가하면 됩니다.
- **코드 외 텍스트 압축** — JSON, Markdown(내부 코드 펜스 포함), 일반 텍스트도 각각 전용 압축기가 있습니다. 구조는 남기고 본문만 덜어내는, 코드 압축기와 같은 방식입니다.
- **내장 보안 스캔** — `secretlint`를 우선 쓰고, 없으면 정규식으로 대체합니다. 민감한 파일은 수집 단계에서 걸러져 다음 단계로 아예 넘어가지 않습니다.
- **검토는 선택 사항** — LLM이 만든 모든 결과물(요약, 룰, 프로젝트 가이드, 의존성 트리)은 저장 전에 사람이 검토·수정할 수 있고, `--auto-correct`로 통째로 건너뛸 수도 있습니다. 파일 선택(`--auto`)과 보정(`--auto-correct`)은 완전히 독립된 옵션이라, CI나 스크립트에서는 `pack`을 아예 비대화형으로 돌릴 수 있습니다.
- **부풀리지 않는 토큰 계산** — GPT-4o, GPT-3.5, GPT-4 인코딩 기준으로 `tiktoken`을 이용해 전/후 토큰을 비교합니다. 단순 압축률이 아니라 실제로 `aif.json`에 담기는 내용을 기준으로 계산해서 숫자가 부풀려지지 않습니다.
- **가벼운 출력, 상세 정보는 필요할 때만** — `aif.json`은 요약과 관계 정보만 담아 가볍게 유지되고, 파일별 압축 코드 전체는 `detail.json`에 따로 저장됩니다. 나중에 MCP 레이어가 생기면 필요한 파일만 골라 불러올 수 있게 하기 위해서입니다.
- **LLM 불안정성에 강함** — 레이트 리밋에 걸리면 백오프를 두고 재시도합니다. 실행이 중간에 실패해도 체크포인트 덕분에 처음부터 다시 할 필요 없이 이어서 진행할 수 있습니다.
- **LLM 프로바이더 독립적** — Gemini를 다른 모델로 바꾸고 싶으면 `generate()` 메서드 하나만 구현해서 등록하면 끝입니다. 나머지 파이프라인은 손댈 필요가 없습니다.
- **git 저장소 전용이 아님** — 일반적인 소프트웨어 저장소가 아니어도 상관없습니다. 게임 모드, 에셋 프로젝트처럼 여러 확장자의 파일이 서로 얽혀 있는 로컬 파일 모음이라면 무엇이든 동작합니다.

## 빠른 시작

```bash
venv\Scripts\activate
pip install -r requirement.txt        # 참고: 파일명에 "s"가 없습니다
```

`.env`에 `GEMINI_API_KEY=...`를 추가한 뒤:

```bash
# 전체 파이프라인: 수집, 스캔, 선택, 압축, 요약, 보정
python src/cli.py pack ./your-project/

# 파일을 직접 고르지 않고 안전한 파일 전체 포함
python src/cli.py pack ./your-project/ --auto

# 보정 단계 없이 LLM 결과를 그대로 사용
python src/cli.py pack ./your-project/ --auto-correct

# 완전 비대화형 실행 (CI, 스크립트용) -- 파일 선택과 보정은 서로 독립된
# 옵션이라 둘을 마음대로 조합해서 써도 됩니다
python src/cli.py pack ./your-project/ --auto --auto-correct

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
| `search <path> <pattern>` | 안전한 파일 전체에서 정규식 검색 (`--context N`, `--ignore-case`) |
| `detail <name>.detail.json <file-key>` | 파일 하나의 압축 본문을 부분만 읽기 (`--start`/`--end`) |
| `select <path>` | 대화형 파일 선택만 |
| `analyze <path>` | LLM 분석만 |
| `signatures \| dependencies \| api \| compress \| debug <file>` | 파일 하나에 대해 추출 단계 하나만 실행 |

</details>

## 테스트

```bash
pip install -r requirement-dev.txt   # requirement.txt에 pytest만 추가됨
pytest
```

압축기, Tree-sitter 추출기, collector의 ignore/바이너리 필터링, 의존성 그래프 연산(`build_tree`/`has_cycle`/`move_file`), 순수 `aif` 편집 API까지 — 네트워크나 `GEMINI_API_KEY` 없이 결정적으로 동작하는 핵심 로직을 커버합니다.

## 출력 포맷

```jsonc
// aif.json — 작고 가벼워서 바로 로드되는 파일
{
  "project": { "name": "...", "prompt": "..." },
  "rules": ["..."],
  "tokens": { "GPT-4o": { "original": 3100, "compressed": 749, "saved_pct": 75.8 } },
  "files": { "src/App.tsx": { "summary": "..." } },
  "relationships": { "src/App.tsx": { "internal": ["..."], "external": ["react"] } }
}
```

```jsonc
// out.detail.json — 더 무겁고, 파일을 자세히 들여다봐야 할 때만 가져옵니다
{
  "src/App.tsx": { "compressed": "import React ...\n    ⋮----\nexport default App" }
}
```

## 기술 스택

Python 3.11 · [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) (Python/Java/TypeScript/JavaScript 문법) · [tiktoken](https://github.com/openai/tiktoken) · Gemini API (`gemini-flash-latest`, `requests`를 통한 순수 REST 호출) · `secretlint` · `pathspec`

## 로드맵

**MCP 통합** — `aif.json`/`detail.json`을 MCP 서버로 노출해서, Claude Code나 Cursor 같은 도구가 프로젝트 컨텍스트를 필요할 때마다 바로 질의할 수 있게 합니다. 우선 요약부터 가져오고, 정말 필요한 파일만 상세 정보를 그때그때 불러오는 방식입니다. *출력 포맷을 이미 lean/detail 구조로 나눠둔 덕분에, 이 작업은 재작성이 아니라 자연스러운 다음 단계가 됩니다.*

**AI로의 선택적 파일 전달** — Ziplex에서 파일을 골라 복사-붙여넣기 없이 대화창에 바로 전달합니다. 파일 내용은 물론 의존성, 시그니처, 요약까지 함께 넘어갑니다.

**모든 파일 타입에 대한 관계 분석** — 의존성 그래프를 코드 파일 너머로 확장합니다. 설정, 텍스트, 바이너리 자산까지 LLM 추론으로 엮어서 하나의 그림으로 만듭니다.

**언어 지원 확대** — GDScript, Lua, ZenScript 같은 게임 개발 전용 언어와 추가 프레임워크까지 Tree-sitter 지원 범위를 넓힙니다.

## 라이선스

[MIT](LICENSE)
