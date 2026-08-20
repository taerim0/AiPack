import json

# 배열: 이 개수를 넘으면 앞쪽 몇 개만 남기고 나머지는 마커로 축약한다.
MAX_ARRAY_ITEMS = 3
# 문자열: 이 길이를 넘으면 잘라내고 마커를 붙인다.
MAX_STRING_LEN = 200

MARKER = "⋮----"


def compress_json(text: str) -> str:
    """JSON 파일을 구조(키)는 유지하고 반복/장문 콘텐츠만 축약해서 돌려준다.

    코드 압축이 함수 시그니처는 남기고 body만 마커로 지우는 것과 같은 원리:
    dict의 키, 짧은 값, 짧은 배열은 그대로 두고
    - MAX_ARRAY_ITEMS를 넘는 배열은 앞쪽 몇 개만 남기고 나머지는 마커로 대체
    - MAX_STRING_LEN을 넘는 문자열은 잘라내고 마커를 붙임
    들여쓰기도 제거해 순수 포맷팅 토큰도 같이 줄인다.

    유효한 JSON이 아니면(파싱 실패) 원본을 그대로 반환한다.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text

    compressed = _compress_value(data)
    return json.dumps(compressed, ensure_ascii=False, separators=(",", ":"))


def _compress_value(value):
    if isinstance(value, dict):
        return {key: _compress_value(v) for key, v in value.items()}

    if isinstance(value, list):
        if len(value) <= MAX_ARRAY_ITEMS:
            return [_compress_value(v) for v in value]

        kept = [_compress_value(v) for v in value[:MAX_ARRAY_ITEMS]]
        remaining = len(value) - MAX_ARRAY_ITEMS
        kept.append(f"{MARKER} ({remaining}개 항목 생략)")
        return kept

    if isinstance(value, str) and len(value) > MAX_STRING_LEN:
        return value[:MAX_STRING_LEN] + f" {MARKER} (생략)"

    return value
