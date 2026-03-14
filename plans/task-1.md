# Task 1: Call an LLM from Code

## LLM Provider Choice

**Provider:** Qwen Code API (remote on VM)

**Model:** `qwen3-coder-plus`

**Reasoning:**
- 1000 free requests per day (sufficient for development and testing)
- Works from Russia without restrictions
- No credit card required
- Strong tool calling capabilities (needed for Tasks 2-3)
- OpenAI-compatible API (easy integration with `openai` Python package)

## Environment Configuration

The agent will read configuration from `.env.agent.secret`:
- `LLM_API_KEY` — API key for authentication
- `LLM_API_BASE` — Base URL of the OpenAI-compatible endpoint
- `LLM_MODEL` — Model name to use

## Agent Architecture

### Input/Output Flow

```
CLI argument (question) → agent.py → LLM API → JSON response → stdout
                              ↓
                         stderr (logs)
```

### Components

1. **Argument Parser** — extracts the question from `sys.argv[1]`
2. **LLM Client** — uses `openai` package to call the LLM with OpenAI-compatible API
3. **Response Formatter** — extracts the answer and formats as JSON
4. **Output Handler** — writes JSON to stdout, logs to stderr

### Error Handling

- Missing API key → exit with error message to stderr
- API timeout (>60s) → exit with error message to stderr
- Invalid response → exit with error message to stderr
- No question provided → exit with usage message to stderr

### Output Format

```json
{"answer": "<LLM response text>", "tool_calls": []}
```

- `answer`: string — the LLM's text response
- `tool_calls`: array — empty for Task 1 (populated in Task 2)

## Testing Strategy

One regression test (`tests/test_agent.py`):
1. Run `agent.py` as subprocess with a test question
2. Parse stdout as JSON
3. Verify `answer` field exists and is non-empty
4. Verify `tool_calls` field exists and is an array

## Dependencies

- `openai` — Python client for OpenAI-compatible APIs (already in `pyproject.toml`)
- `python-dotenv` — for loading `.env.agent.secret` (already in `pyproject.toml`)
