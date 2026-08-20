import re

# 리스트: 이 개수를 넘는 연속 항목은 앞쪽 몇 개만 남기고 마커로 축약한다.
MAX_LIST_ITEMS = 5
# 문단: 이 길이를 넘으면 잘라내고 마커를 붙인다. (json_compressor의 MAX_STRING_LEN과 동일 기준)
MAX_PARAGRAPH_LEN = 200
# 코드 블록: 이 줄 수를 넘으면 앞쪽 몇 줄만 남기고 마커로 축약한다.
MAX_CODEBLOCK_LINES = 10
# 표: 헤더/구분선을 뺀 데이터 행이 이 개수를 넘으면 앞쪽 몇 행만 남긴다.
MAX_TABLE_ROWS = 5

MARKER = "⋮----"

_LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")

# 코드블록 언어 태그(```python 등) -> extract/code가 아는 확장자.
# languages.py의 LANGUAGE_CONFIGS 키(.py/.java/.ts/.js)에 맞춰뒀다 — 거기 언어가
# 늘어나면 여기도 별칭을 추가해야 그 언어 코드블록이 구조 압축의 혜택을 받는다.
_FENCE_LANG_TO_EXT = {
    "python": ".py",
    "py": ".py",
    "java": ".java",
    "typescript": ".ts",
    "ts": ".ts",
    "javascript": ".js",
    "js": ".js",
    "jsx": ".js",
    "tsx": ".ts",
}


def compress_markdown(text: str) -> str:
    """마크다운을 구조(헤딩)는 유지하고 반복/장문 콘텐츠만 축약해서 돌려준다.

    코드 압축이 함수 시그니처는 남기고 body만 마커로 지우는 것과 같은 원리를
    라인 단위 마크다운에 적용한다:
    - 헤딩(#...)과 빈 줄은 그대로 유지 (문서 구조 자체이므로)
    - MAX_LIST_ITEMS를 넘는 연속 리스트 항목은 앞쪽만 남기고 마커로 대체
    - 코드 블록: 펜스에 언어 태그가 있고 extract/code가 아는 언어면(.py/.java/.ts/.js)
      compress_code()로 함수 시그니처만 남기고 body를 지우는 "진짜" 구조 압축을
      먼저 적용한다. 그 결과가 여전히 MAX_CODEBLOCK_LINES를 넘으면(함수가 없는
      평범한 스크립트 등) 앞쪽만 남기고 마커로 자른다. 언어 미지정/미지원이면
      곧바로 줄 수 기준으로만 자른다. 여는/닫는 펜스는 항상 유지.
    - MAX_TABLE_ROWS를 넘는 표 데이터 행은 앞쪽만 남기고 마커로 대체
      (헤더 행 + 구분선은 항상 유지)
    - MAX_PARAGRAPH_LEN을 넘는 일반 문단은 잘라내고 마커를 붙임

    Tree-sitter 마크다운 문법이 없어 정식 AST 파싱은 아니고, 정규식 기반의
    라인 단위 근사 파싱이다 — json_compressor처럼 "실패하면 원본 그대로"
    전략을 쓸 파싱 실패 케이스가 없으므로(마크다운은 늘 "유효"하다)
    항상 압축을 시도한다.
    """
    lines = text.splitlines()
    result: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        if _FENCE_RE.match(line):
            i = _compress_codeblock(lines, i, result)
            continue

        if _LIST_ITEM_RE.match(line):
            i = _compress_list(lines, i, result)
            continue

        if _TABLE_ROW_RE.match(line):
            i = _compress_table(lines, i, result)
            continue

        if line.strip() == "" or _HEADING_RE.match(line):
            result.append(line)
            i += 1
            continue

        i = _compress_paragraph(lines, i, result)

    return "\n".join(result)


def _compress_codeblock(lines: list[str], i: int, result: list[str]) -> int:
    fence_line = lines[i]
    fence = _FENCE_RE.match(fence_line).group(1)
    lang = fence_line.strip().removeprefix(fence).strip().lower()
    result.append(fence_line)
    i += 1

    body_start = i
    n = len(lines)
    while i < n and not lines[i].strip().startswith(fence):
        i += 1
    body = lines[body_start:i]

    body = _compress_codeblock_body(body, lang)

    if len(body) > MAX_CODEBLOCK_LINES:
        result.extend(body[:MAX_CODEBLOCK_LINES])
        remaining = len(body) - MAX_CODEBLOCK_LINES
        result.append(f"{MARKER} ({remaining}줄 생략)")
    else:
        result.extend(body)

    if i < n:  # 닫는 펜스
        result.append(lines[i])
        i += 1

    return i


def _compress_codeblock_body(body: list[str], lang: str) -> list[str]:
    ext = _FENCE_LANG_TO_EXT.get(lang)
    if not ext:
        return body

    # 지연 import: 순환 참조 방지 이유는 compressor.py의 compress_file() 쪽
    # 주석 참고. extract.code.compressor -> extract.text.registry ->
    # markdown_compressor -> extract.code.compressor로 이어지는 고리를
    # 함수 안 import로 끊는다.
    from extract.code.compressor import compress_code

    compressed = compress_code("\n".join(body), ext)
    return body if compressed is None else compressed.splitlines()


def _compress_list(lines: list[str], i: int, result: list[str]) -> int:
    items = []
    n = len(lines)
    while i < n and _LIST_ITEM_RE.match(lines[i]):
        items.append(lines[i])
        i += 1

    if len(items) > MAX_LIST_ITEMS:
        result.extend(items[:MAX_LIST_ITEMS])
        remaining = len(items) - MAX_LIST_ITEMS
        result.append(f"{MARKER} ({remaining}개 항목 생략)")
    else:
        result.extend(items)

    return i


def _compress_table(lines: list[str], i: int, result: list[str]) -> int:
    rows = []
    n = len(lines)
    while i < n and _TABLE_ROW_RE.match(lines[i]):
        rows.append(lines[i])
        i += 1

    # 헤더 행 + 구분선(| --- | --- |)은 항상 유지, 그 이후 데이터 행만 개수 제한
    header = rows[:2]
    data_rows = rows[2:]
    result.extend(header)

    if len(data_rows) > MAX_TABLE_ROWS:
        result.extend(data_rows[:MAX_TABLE_ROWS])
        remaining = len(data_rows) - MAX_TABLE_ROWS
        result.append(f"{MARKER} ({remaining}개 행 생략)")
    else:
        result.extend(data_rows)

    return i


def _compress_paragraph(lines: list[str], i: int, result: list[str]) -> int:
    n = len(lines)
    para_start = i
    while (
        i < n
        and lines[i].strip() != ""
        and not _LIST_ITEM_RE.match(lines[i])
        and not _TABLE_ROW_RE.match(lines[i])
        and not _FENCE_RE.match(lines[i])
        and not _HEADING_RE.match(lines[i])
    ):
        i += 1

    para_lines = lines[para_start:i]
    para_text = "\n".join(para_lines)

    if len(para_text) > MAX_PARAGRAPH_LEN:
        result.append(para_text[:MAX_PARAGRAPH_LEN] + f" {MARKER} (생략)")
    else:
        result.extend(para_lines)

    return i
