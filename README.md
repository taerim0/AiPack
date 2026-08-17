# Ziplex

A tool that converts local projects into structured contexts that AI can understand instantly.

---

## Features

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

## Roadmap

**Selective File Delivery to AI**

While working with AI on debugging or code review, users can select specific files directly from Ziplex and send them instantly — without copy-pasting. The AI receives not just the file content, but its full context from AIF.json: dependencies, signatures, and summary. One click, full context.

**MCP Integration**

Expose AIF.json as an MCP server so AI tools like Claude Code and Cursor can query project context on demand — automatically pulling the latest state without manual re-export.

**Relationship Analysis Across All File Types**

Extend dependency mapping beyond code files. Detect relationships between text, config, and binary files using LLM inference, building a complete picture of how every file connects.

**Expanded Language Support**

Broader Tree-sitter coverage for game-specific languages (GDScript, Lua, ZenScript) and additional frameworks, making Ziplex useful across more project types.
