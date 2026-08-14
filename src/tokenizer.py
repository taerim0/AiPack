import tiktoken

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