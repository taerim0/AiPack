import tiktoken

from compressor import compress_file

MODEL_ENCODINGS = {
    "GPT-4o":  "o200k_base",
    "GPT-3.5": "cl100k_base",
    "GPT-4":   "cl100k_base",
}

MODEL_MAX_TOKENS = {
    "GPT-4o":  128_000,
    "GPT-3.5": 16_000,
    "GPT-4":   128_000,
}

def count_tokens(text: str, encoding_name: str) -> int:
    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode(text))


def analyze_tokens(file_paths: list[str]) -> tuple:
    combined = ""
    for file_path in file_paths:
        try:
            content = open(file_path, "r", encoding="utf-8").read()
            combined += f"\n### {file_path}\n{content}\n"
        except (UnicodeDecodeError, IsADirectoryError):
            continue

    results = {}
    for model, encoding in MODEL_ENCODINGS.items():
        token_count = count_tokens(combined, encoding)
        max_tokens = MODEL_MAX_TOKENS[model]
        percentage = (token_count / max_tokens) * 100
        filled = int(percentage / 10)
        bar = "█" * filled + "░" * (10 - filled)

        results[model] = {
            "tokens": token_count,
            "max": max_tokens,
            "percentage": round(percentage, 1),
            "bar": bar
        }

    return results, combined

def analyze_tokens_with_compression(file_paths: list[str]) -> tuple:
    original_text = ""
    compressed_text = ""

    for file_path in file_paths:
        try:
            content = open(file_path, "r", encoding="utf-8").read()
            original_text += f"\n### {file_path}\n{content}\n"

            compressed = compress_file(file_path)
            compressed_text += f"\n### {file_path}\n{compressed}\n"
        except (UnicodeDecodeError, IsADirectoryError):
            continue

    results = {}
    for model, encoding in MODEL_ENCODINGS.items():
        original_count = count_tokens(original_text, encoding)
        compressed_count = count_tokens(compressed_text, encoding)
        max_tokens = MODEL_MAX_TOKENS[model]

        saved = original_count - compressed_count
        saved_pct = round((saved / original_count) * 100, 1) if original_count > 0 else 0

        original_pct = (original_count / max_tokens) * 100
        compressed_pct = (compressed_count / max_tokens) * 100

        filled_o = int(original_pct / 10)
        filled_c = int(compressed_pct / 10)

        results[model] = {
            "original":       original_count,
            "compressed":     compressed_count,
            "saved":          saved,
            "saved_pct":      saved_pct,
            "max":            max_tokens,
            "original_bar":   "█" * filled_o + "░" * (10 - filled_o),
            "compressed_bar": "█" * filled_c + "░" * (10 - filled_c),
        }

    return results, compressed_text