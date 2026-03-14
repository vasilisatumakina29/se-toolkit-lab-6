# Agent Architecture

## Overview

This is a CLI agent that connects to an LLM and answers questions. It serves as the foundation for the more advanced agent with tools and agentic loop (Tasks 2-3).

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  CLI Argument   │ ──> │   agent.py   │ ──> │  LLM API    │ ──> │  JSON Output │
│  (question)     │     │  (parser +   │     │  (Qwen)     │     │  (stdout)    │
│                 │     │   client)    │     │             │     │              │
└─────────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
                              │
                              ▼
                         stderr (logs)
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
- Sends chat completion request with system + user messages

### 4. Response Formatter

- Extracts the answer from the LLM response
- Formats as JSON with required fields:
  - `answer`: the LLM's text response
  - `tool_calls`: empty array (reserved for Task 2)

### 5. Output Handler

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
uv run agent.py "What does REST stand for?"

# Example output
{"answer": "Representational State Transfer.", "tool_calls": []}
```

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `.env.agent.secret` | Exit with error to stderr |
| Missing `LLM_API_KEY` | Exit with error to stderr |
| No question provided | Exit with usage message to stderr |
| API timeout | Exit with error (OpenAI client timeout) |
| Invalid API response | Exit with error to stderr |

## Testing

Run the regression test:

```bash
uv run pytest tests/test_agent.py -v
```

The test:
1. Runs `agent.py` as a subprocess
2. Parses stdout as JSON
3. Verifies `answer` and `tool_calls` fields exist

## Dependencies

- `openai` — Python client for OpenAI-compatible APIs
- `python-dotenv` — loads `.env.agent.secret`

Both are already listed in `pyproject.toml`.

## Future Extensions (Tasks 2-3)

- **Task 2:** Add tools (file read, API query, etc.)
- **Task 3:** Add agentic loop (plan → act → observe)
- System prompt will be expanded with tool definitions
- `tool_calls` array will be populated with actual tool invocations
