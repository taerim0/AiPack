from pathlib import Path
from tree_sitter import Parser

from extract.code.languages import get_language_config


def get_parser(file_path: str) -> Parser | None:
    ext = Path(file_path).suffix
    config = get_language_config(ext)
    if not config:
        return None
    return Parser(config.language)
