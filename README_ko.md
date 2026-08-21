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

- **다국어 코드 압축** — 지금은 Python, Java, TypeScript, JavaScript, Lua, GDScript를 지원합니다. 언어별 설정을 테이블(`LanguageConfig`) 하나로 관리해서, 새 문법을 추가할 때 코드를 갈아엎을 필요 없이 항목 하나만 추가하면 됩니다.
- **코드 외 텍스트 압축** — JSON, Markdown(내부 코드 펜스 포함), 일반 텍스트도 각각 전용 압축기가 있습니다. 구조는 남기고 본문만 덜어내는, 코드 압축기와 같은 방식입니다.
- **내장 보안 스캔** — `secretlint`를 우선 쓰고, 없으면 정규식으로 대체합니다. 민감한 파일은 수집 단계에서 걸러져 다음 단계로 아예 넘어가지 않습니다.
- **검토는 선택 사항** — LLM이 만든 모든 결과물(요약, 룰, 프로젝트 가이드, 의존성 트리)은 저장 전에 사람이 검토·수정할 수 있고, `--auto-correct`로 통째로 건너뛸 수도 있습니다. 파일 선택(`--auto`)과 보정(`--auto-correct`)은 완전히 독립된 옵션이라, CI나 스크립트에서는 `pack`을 아예 비대화형으로 돌릴 수 있습니다.
- **프로젝트 규모가 아니라 필요한 만큼만 검토** — 파일이 수백 개면 요약을 하나하나 사람이 다 보는 게 애초에 불가능합니다. 각 요약마다 LLM 호출 없이 무료로 계산되는 신뢰도 점수(0.0~1.0, 요약 문구가 파일의 실제 시그니처와 얼마나 겹치는지)가 붙고, 보정 단계에선 의심스러운 것만 사람에게 물어보고 나머지는 자동으로 유지합니다. 이 점수는 `aif.json`에도 그대로 실려서, 에이전트가 `get_detail`로 한 번 더 확인해볼지 판단하는 데 쓸 수 있습니다.
- **부풀리지 않는 토큰 계산** — GPT-4o, GPT-3.5, GPT-4 인코딩 기준으로 `tiktoken`을 이용해 전/후 토큰을 비교합니다. 단순 압축률이 아니라 실제로 `aif.json`에 담기는 내용을 기준으로 계산해서 숫자가 부풀려지지 않습니다.
- **가벼운 출력, 상세 정보는 필요할 때만** — `aif.json`은 요약과 관계 정보만 담아 가볍게 유지되고, 파일별 압축 코드 전체는 `detail.json`에 따로 저장됩니다. 모든 파일에 기본으로 딸려가는 대신, MCP 서버의 `get_detail` 툴(아래 참고)이 필요할 때만 불러옵니다.
- **LLM 불안정성에 강함** — 레이트 리밋에 걸리면 백오프를 두고 재시도합니다. 실행이 중간에 실패해도 체크포인트 덕분에 처음부터 다시 할 필요 없이 이어서 진행할 수 있습니다.
- **Incremental re-pack** — 콘텐츠 해시 매니페스트(`<name>.cache.json`)로, 같은 프로젝트를 다시 `pack`할 때 안 바뀐 파일은 요약을 재사용하고 LLM 호출을 아낍니다. 그래서 `aif.json`을 자주 최신 상태로 유지하는 게 실제로 부담 없어집니다. 얼마나 오래됐는지만 확인하고 싶을 땐 재-pack 없이 `check_freshness`로 따로 확인할 수도 있습니다(아래 MCP 서버 참고).
- **LLM 프로바이더 독립적** — Gemini를 다른 모델로 바꾸고 싶으면 `generate()` 메서드 하나만 구현해서 등록하면 끝입니다. 나머지 파이프라인은 손댈 필요가 없습니다.
- **git 저장소 전용이 아님** — 일반적인 소프트웨어 저장소가 아니어도 상관없습니다. 게임 모드, 에셋 프로젝트처럼 여러 확장자의 파일이 서로 얽혀 있는 로컬 파일 모음이라면 무엇이든 동작합니다.
- **CLI 없이 쓰는 로컬 GUI** — 터미널 대신 네이티브 창(또는 일반 브라우저 탭)에서 프로젝트를 패킹하고, 요약을 검토하고, 관계를 편집할 수 있습니다. 같은 GUI가 Claude Code나 MCP를 쓸 수 없는 환경에서 이미 패킹된 프로젝트를 둘러보는 읽기 전용 브라우저 역할도 합니다(아래 [GUI](#gui) 참고).

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

# 이전 pack 결과 무시하고 모든 파일 요약을 강제로 다시 생성
python src/cli.py pack ./your-project/ --no-cache
```

전에 한 번 pack한 프로젝트를 다시 pack하면, 실제로 내용이 바뀐 파일(콘텐츠 해시 기준)만 다시 요약합니다 — 나머지는 이전 요약을 그대로 재사용해서 LLM을 다시 호출하지 않습니다.

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
| `freshness <path> <name>.cache.json` | `aif.json`이 디스크의 실제 파일과 맞는지 해시로 확인 — LLM 호출 없음 |
| `select <path>` | 대화형 파일 선택만 |
| `analyze <path>` | LLM 분석만 |
| `signatures \| dependencies \| api \| compress \| debug <file>` | 파일 하나에 대해 추출 단계 하나만 실행 |

</details>

## 테스트

```bash
pip install -r requirement-dev.txt   # requirement.txt에 pytest만 추가됨
pytest
```

압축기, Tree-sitter 추출기, collector의 ignore/바이너리 필터링, 의존성 그래프 연산(`build_tree`/`has_cycle`/`move_file`), 순수 `aif` 편집 API까지 — 네트워크나 `GEMINI_API_KEY` 없이 결정적으로 동작하는 핵심 로직을 커버합니다. 여기에 더해 Gemini 대신 네트워크 없는 `MockProvider`로 `pack()` 전체를 실제로 한 번 돌려서, 체크포인트·병렬 요약·토큰 계산까지 실제 LLM 호출의 비용·대기시간 없이 검증합니다.

실제 프로젝트로 `pack`을 빠르게 스모크테스트하고 싶다면: `LLM_PROVIDER=mock python src/cli.py pack <project> --auto --auto-correct`로 1초 안에 네트워크 없이 전체 파이프라인을 돌릴 수 있습니다.

## 출력 포맷

```jsonc
// aif.json — 작고 가벼워서 바로 로드되는 파일
{
  "project": { "name": "...", "prompt": "..." },
  "rules": ["..."],
  "tokens": { "GPT-4o": { "original": 3100, "compressed": 749, "saved_pct": 75.8 } },
  "files": { "src/App.tsx": { "summary": "...", "confidence": 0.83 } },
  "relationships": { "src/App.tsx": { "internal": ["..."], "external": ["react"] } }
}
```

```jsonc
// out.detail.json — 더 무겁고, 파일을 자세히 들여다봐야 할 때만 가져옵니다
{
  "src/App.tsx": { "compressed": "import React ...\n    ⋮----\nexport default App" }
}
```

```jsonc
// out.cache.json — AI가 읽는 파일이 아니라 내부 관리용입니다. check_freshness가
// 나중에 비교할 수 있도록 패킹 시점 파일 내용의 해시를 저장해둡니다
{
  "src/App.tsx": "3b1c2e...(sha256)"
}
```

## MCP 서버

Claude Code, Cursor 등 MCP 클라이언트에서 이미 패킹된 프로젝트를 바로 질의할 수 있습니다 — `aif.json`을 프롬프트에 복사-붙여넣기할 필요 없이요.

```bash
python src/mcp_server.py                              # 직접 실행 (stdio 트랜스포트)
claude mcp add ziplex -- python src/mcp_server.py      # Claude Code에 등록 (레포 루트에서)
```

| 툴 | 하는 일 |
|---|---|
| `get_overview(aif_path, project_path?)` | 프로젝트 가이드, 코딩 룰, 토큰 통계 — 가장 먼저 호출하면 됩니다 |
| `list_files(aif_path, project_path?)` | 모든 파일을 요약 + 신뢰도 점수와 함께 매핑 |
| `get_dependents(aif_path, file)` | `file`을 직접 의존하는 파일들 |
| `get_blast_radius(aif_path, file)` | `file`이 바뀌면 직간접적으로 영향받는 모든 파일 |
| `get_detail(aif_path, file, start_line?, end_line?)` | 파일의 압축 소스, 전체 또는 줄 범위로 |
| `check_freshness(project_path, aif_path)` | 패킹 결과가 디스크의 실제 파일과 맞는지 해시로 확인 — LLM 호출 없음 |
| `search_project(project_path, pattern, ...)` | 프로젝트 원본 파일 전체에서 정규식 검색 |

의도적으로 읽기 전용입니다 — 모든 툴은 사람이 `correct_aif()`로 이미 검토한 `aif.json`/`detail.json`을 그대로 서빙할 뿐, 어떤 툴도 프로젝트를 알아서 다시 패킹하거나 보정하지 않습니다. 그건 Ziplex의 핵심인 human-in-the-loop 단계를 건너뛰는 거니까요. `get_dependents`/`get_blast_radius`도 `pack`이 만드는 것과 같은, 사람이 보정한 `relationships` 그래프 위에서 동작합니다 — 방금 추출한 검토 안 된 그래프가 아니라요.

`aif.json`/`detail.json`은 마지막 `pack` 실행 시점의 스냅샷이라, 활발히 바뀌는 프로젝트에서는 실제 상태와 어긋날 수 있습니다. `search_project`(항상 파일을 직접 읽음)를 제외한 나머지 툴은 전부 이 스냅샷을 그대로 믿습니다 — 오래됐을까 걱정되면 `check_freshness`부터 호출하거나, `get_overview`/`list_files`에 `project_path`를 함께 넘겨서 알아서 확인하게 하세요: 스냅샷이 오래됐으면 결과에 `_stale` 필드가 추가로 붙어서 옵니다. 뭘 고쳐주진 않지만, 나머지를 믿기 전에 다시 `pack`할 필요가 있는지는 알려줍니다.

## GUI

터미널을 쓰지 않고 프로젝트를 패킹하거나, Claude Code(또는 MCP 자체)를 쓸 수 없지만 브라우저 기반 AI 챗은 쓸 수 있는 환경에서 이미 패킹된 프로젝트를 둘러보는 용도의 로컬 단일 사용자 GUI입니다.

```bash
python src/gui_server.py                                            # 네이티브 창 (pywebview)
python src/gui_server.py --aif out.json --project ./your-project/   # 시작 화면 미리 채우기
python src/gui_server.py --no-window                                # 창 대신 일반 브라우저 탭
```

**GUI에서 패킹하기** — 네이티브 폴더 선택창으로 프로젝트 폴더를 고르고, 어떤 파일을 포함할지 체크박스로 고른 뒤(`collect`의 보안 스캔이 만드는 것과 같은 safe/dangerous 구분), 백그라운드에서 돌아가는 패킹 과정을 지켜봅니다. 분석이 끝나면 저장 전에 검토 단계에서 멈춥니다 — 프로젝트 이름, 가이드, 룰, 파일별 요약을 고칠 수 있고(CLI와 같은 기준으로 신뢰도가 낮은 것만 검토 대상으로 표시됩니다), 의존성 그래프도 엣지 하나하나를 잇거나 끊는 방식으로 조정할 수 있습니다 — 부모가 여러 개인 파일이라도 다른 참조는 그대로 남습니다.

**기존 pack 둘러보기** — MCP 서버가 노출하는 overview/files/dependents/blast-radius/detail/search 뷰를 MCP 툴 호출 대신 웹 페이지로 그대로 씁니다. 각 페이지엔 복사 버튼이 있고, 의도된 흐름은 여기서 둘러본 다음 필요한 내용을 별도의 AI 챗에 직접 붙여넣는 것입니다 — GUI가 그 챗과 직접 통신하지는 않습니다.

`127.0.0.1`에만 바인딩됩니다 — `--host` 옵션이 없고, 네트워크에 노출할 방법도 없습니다.

## 팀에서 사용하기

Ziplex는 한 사람의 로컬 스냅샷을 패킹합니다 — 공유 서버나 실시간 동기화는 없습니다. 그렇다고 팀에서 못 쓴다는 건 아닙니다: `aif.json`/`detail.json`/`cache.json`은 그냥 파일이라, 다른 자동 생성 산출물처럼 프로젝트 저장소에 커밋해서 팀이 하나의 기준선을 공유할 수 있습니다.

- 의미 있는 변경 뒤에 `pack`을 돌린 사람이 코드 변경과 함께 새로 생성된 결과물을 커밋합니다.
- 다른 사람들의 `aif.json`은 마지막으로 커밋된 시점만큼만 최신입니다 — `check_freshness`(또는 위에서 설명한, `project_path`를 넘긴 `get_overview`/`list_files`)로 자기 작업 사본이 커밋된 것과 얼마나 어긋났는지 다시 `pack`하지 않고도 확인할 수 있습니다.
- 이건 실시간 동기화가 아니라 권장 컨벤션입니다 — Ziplex가 강제하거나 조율하지 않습니다. 병합/충돌 해결도 없고, 두 사람이 각자 커밋하기 전에 따로 `pack`을 돌리면 "누구 결과가 맞는지"도 정해져 있지 않습니다.

## 기술 스택

Python 3.11 · [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) (Python/Java/TypeScript/JavaScript/Lua/GDScript 문법, GDScript는 `tree-sitter-language-pack` 경유) · [tiktoken](https://github.com/openai/tiktoken) · Gemini API (`gemini-flash-latest`, `requests`를 통한 순수 REST 호출) · [MCP](https://modelcontextprotocol.io/) · Flask · pywebview · `secretlint` · `pathspec`

## 로드맵

**AI로의 선택적 파일 전달** — Ziplex에서 파일을 골라 복사-붙여넣기 없이 대화창에 바로 전달합니다. 파일 내용은 물론 의존성, 시그니처, 요약까지 함께 넘어갑니다. *(읽기 전용으로 "둘러보고 직접 복사"하는 절반은 위 [GUI](#gui)로 이미 나왔습니다 — 아직 남은 건 그 전달을 자동화하는 부분입니다.)*

**모든 파일 타입에 대한 관계 분석** — 의존성 그래프를 코드 파일 너머로 확장합니다. 설정, 텍스트, 바이너리 자산까지 LLM 추론으로 엮어서 하나의 그림으로 만듭니다.

**언어 지원 확대** — 게임 개발 전용 언어와 추가 프레임워크까지 Tree-sitter 지원 범위를 넓힙니다. Lua와 GDScript는 지원 완료 (GDScript는 전용 PyPI 패키지가 없어서 `tree-sitter-language-pack`에 번들된 문법을 대신 씁니다). ZenScript(마이너한 Minecraft 모딩 DSL)는 이 시점 기준 관리되는 Tree-sitter 문법 자체가 안 보여서 아직 열려있는 항목입니다.

## 라이선스

[MIT](LICENSE)
