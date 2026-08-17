## Ziplex

A tool that converts local projects into structured contexts that AI can understand instantly.

---

- Solves the problems that prevent AI from understanding projects

| Problem | Cause | Solution |
|---------|-------|----------|
| Context Overflow | Exceeds token limit | Tree-sitter compression + tiktoken |
| Lost in the Middle | Middle content lost in long context | Structured AIF.json |
| Attention Dilution | Focus diluted by excessive tokens | Summary-based lightweight output |
| Semantic Gap | No file relationship information | Explicit dependencies |

- Supports all local projects

Beyond Git repositories — game mods, asset projects, and any collection of local files with relationships across various file extensions.

- Automatic security scanning (Secretlint)

Automatically detects and excludes files containing sensitive information such as API keys, passwords, and tokens.

- Token reduction

Removes code implementation bodies via Tree-sitter, delivering the same information with significantly fewer tokens.

- LLM Summary + User correction

Users review and refine AI-generated results. Combines automatic generation with human judgment for optimal context.

```bash
# Pack a project
python src/cli.py pack ./your-project/

# Auto-select all files
python src/cli.py pack ./your-project/ --auto

# Specify output file
python src/cli.py pack ./your-project/ -o output/aif.json
```
