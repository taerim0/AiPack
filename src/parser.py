from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_java as tsjava
import tree_sitter_typescript as tstypescript

LANGUAGE_MAP = {
    ".py":   Language(tspython.language()),
    ".java": Language(tsjava.language()),
    ".ts":   Language(tstypescript.language_typescript()),
    ".js":   Language(tstypescript.language_tsx()),
}

def get_parser(file_path: str) -> Parser | None:
    ext = Path(file_path).suffix
    language = LANGUAGE_MAP.get(ext)
    if not language:
        return None
    parser = Parser(language)
    return parser