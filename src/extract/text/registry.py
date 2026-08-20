"""AST가 없는 텍스트 파일(json 등)의 압축 함수를 확장자별로 등록해둔다.

extract/code/languages.py가 Tree-sitter 언어별 설정을 한 곳에 모으는 것과 같은
방식으로, 여기서는 확장자 -> 압축 함수만 등록한다. 새 텍스트 포맷을 지원하려면
이 파일에 압축 함수를 만들고 TEXT_COMPRESSORS에 등록하면 된다.
"""

from typing import Callable

from extract.text.json_compressor import compress_json
from extract.text.markdown_compressor import compress_markdown

TEXT_COMPRESSORS: dict[str, Callable[[str], str]] = {
    ".json": compress_json,
    ".md": compress_markdown,
}


def get_text_compressor(ext: str) -> Callable[[str], str] | None:
    return TEXT_COMPRESSORS.get(ext)
