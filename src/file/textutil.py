def read_text(file_path: str) -> str | None:
    """Safely reads a file as UTF-8 text.

    Returns None instead of raising on binary files, encoding issues, or
    inaccessible paths (directories, permissions, etc.). This is the shared
    entry point that keeps the pipeline from crashing on projects with
    non-text files mixed in (game assets like images, sound, etc.).
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except (UnicodeDecodeError, OSError):
        return None
