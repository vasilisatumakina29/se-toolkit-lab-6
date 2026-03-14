# Agent Architecture

## Overview

This is a CLI agent that connects to an LLM and answers questions using **tools** and an **agentic loop**. The agent can read files from the project wiki and list directory contents to find accurate answers with source citations.

## Architecture

```
┌─────────────────┐     ┌──────────────────────────────────┐     ┌─────────────┐
│  CLI Argument   │ ──> │  agent.py (Agentic Loop)         │ ──> │  LLM API    │
│  (question)     │     │  - Tool execution                │     │  (Qwen)     │
│                 │     │  - Message history management    │     │             │
└─────────────────┘     └──────────────────────────────────┘     └─────────────┘
         │                        │                                      │
         │                        ▼                                      │
         │                 ┌──────────────────┐                          │
         │                 │  Tools           │                          │
         │                 │  - read_file     │◄─────────────────────────┘
         │                 │  - list_files    │
         │                 └──────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│  JSON Output    │     │  stderr (logs)   │
│  (stdout)       │     │                  │
└─────────────────┘     └──────────────────┘
```

## Components

### 1. Argument Parser (`agent.py`)

- Reads the question from `sys.argv[1]`
- Validates that a question was provided
- Exits with usage message if no argument

### 2. Configuration Loader

- Loads `.env.agent.secret` from the project root
- Extracts `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
- Validates that all required fields are present

### 3. LLM Client

- Uses the `openai` Python package (OpenAI-compatible API)
- Connects to the configured endpoint
- Sends chat completion requests with tool definitions

### 4. Tools

#### `read_file(path: str) -> str`

Reads the contents of a file from the project repository.

**Parameters:**
- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:**
- File contents as a string
- Error message if file doesn't exist or path is invalid

**Security:**
- Rejects paths containing `..` (path traversal prevention)
- Validates that resolved path is within project directory

#### `list_files(path: str) -> str`

Lists files and directories at a given path.

**Parameters:**
- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:**
- Newline-separated listing of entries
- `[DIR]` prefix for directories
- Error message if directory doesn't exist or path is invalid

**Security:**
- Same path validation as `read_file`

### 5. Agentic Loop

The agentic loop enables iterative tool usage:

```python
messages = [system_prompt, user_question]
tool_calls_log = []

for iteration in range(MAX_TOOL_CALLS):
    # 1. Call LLM with messages + tool definitions
    response = client.chat.completions.create(...)
    
    # 2. Check for tool calls
    if message.tool_calls:
        # Execute each tool
        for tool_call in message.tool_calls:
            result = execute_tool(tool_call)
            tool_calls_log.append({...})
        
        # Append results to messages
        messages.append(tool_results)
    
    # 3. No tool calls = final answer
    else:
        answer, source = parse_response(message.content)
        break
```

**Loop behavior:**
1. Send user question + tool definitions to LLM
2. If LLM responds with `tool_calls` → execute tools, append results as `tool` role messages, repeat
3. If LLM responds with text (no tool calls) → parse answer and source, output JSON
4. Maximum 10 tool calls per question

### 6. System Prompt

The system prompt instructs the LLM to:

1. **Use tools strategically:**
   - First use `list_files` to discover wiki files
   - Then use `read_file` to find specific answers

2. **Follow a workflow:**
   - Discover relevant files
   - Read files to find answers
   - Identify section headers for source citation

3. **Output in a specific format:**
   ```
   ANSWER: <concise answer>
   SOURCE: <file_path>#<section_anchor>
   ```

### 7. Response Parser

Extracts `answer` and `source` from LLM response using regex:
- `ANSWER:\s*(.+)` → answer text
- `SOURCE:\s*(.+)` → source reference (e.g., `wiki/git-workflow.md#merge-the-pr`)

### 8. Output Formatter

Formats output as JSON with required fields:
- `answer`: string — the extracted answer
- `source`: string — file path + section anchor
- `tool_calls`: array — all tool invocations with args and results

### 9. Output Handler

- Writes JSON to stdout (for piping/automation)
- Writes debug logs to stderr (for human readability)

## LLM Provider

**Provider:** Qwen Code API (deployed on VM)

**Model:** `qwen3-coder-plus`

**Why Qwen Code:**
- 1000 free requests per day
- Works from Russia
- No credit card required
- OpenAI-compatible API
- Strong tool calling capabilities

## Configuration

Create `.env.agent.secret` in the project root:

```bash
cp .env.agent.example .env.agent.secret
```

Fill in the values:

```env
LLM_API_KEY=your-api-key-here
LLM_API_BASE=http://<your-vm-ip>:<port>/v1
LLM_MODEL=qwen3-coder-plus
```

> **Note:** This is different from `.env.docker.secret` which configures the backend LMS API.

## Usage

```bash
# Basic usage
uv run agent.py "How do you resolve a merge conflict?"

# Example output
{
    "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
    "source": "wiki/git-workflow.md#merge-the-pr",
    "tool_calls": [
        {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
        {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
    ]
}
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit with error to stderr |
| Missing `LLM_API_KEY` | Exit with error to stderr |
| No question provided | Exit with usage message to stderr |
| Path traversal attempt | Return error message to LLM |
| File not found | Return error message to LLM |
| Max iterations reached | Return partial answer with tool_calls log |
| API timeout | Exit with error (OpenAI client timeout) |
| Invalid API response | Exit with error to stderr |

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

Tests verify:
1. Agent runs successfully with a question argument
2. Outputs valid JSON to stdout
3. Contains required fields: `answer`, `source`, `tool_calls`
4. Tool calls are logged with correct structure

## Dependencies

- `openai` — Python client for OpenAI-compatible APIs
- `python-dotenv` — loads `.env.agent.secret`

Both are already listed in `pyproject.toml`.

## Security Considerations

### Path Traversal Prevention

Both tools validate paths to prevent accessing files outside the project directory:

```python
def validate_path(relative_path: str, project_root: Path) -> Path:
    # Reject paths with .. traversal
    if ".." in relative_path:
        raise ValueError(f"Path traversal not allowed: {relative_path}")
    
    # Resolve to absolute path
    resolved = (project_root / relative_path).resolve()
    
    # Ensure it's within project root
    if not str(resolved).startswith(str(project_root.resolve())):
        raise ValueError(f"Access denied: {relative_path}")
    
    return resolved
```

### Tool Call Limit

Maximum 10 tool calls per question prevents infinite loops and excessive API usage.

## Future Extensions (Task 3)

- Add more tools (`query_api`, `search_code`, etc.)
- Implement planning phase before tool execution
- Add memory/context management for multi-turn conversations
