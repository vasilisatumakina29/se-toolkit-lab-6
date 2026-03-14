# Task 2: The Documentation Agent — Implementation Plan

## Overview

This task extends the Task 1 agent with **tools** (`read_file`, `list_files`) and an **agentic loop** that allows the LLM to iteratively query the project wiki before providing an answer.

---

## Tool Schemas

### Approach

I will define tools using the **OpenAI function-calling format**. Each tool has:
- `name`: the tool identifier
- `description`: what the tool does and when to use it
- `parameters`: JSON Schema defining the arguments

### Tool Definitions

#### `read_file`

```python
{
    "name": "read_file",
    "description": "Read the contents of a file from the project repository. Use this to find specific information in documentation files.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
            }
        },
        "required": ["path"]
    }
}
```

#### `list_files`

```python
{
    "name": "list_files",
    "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative directory path from project root (e.g., 'wiki')"
            }
        },
        "required": ["path"]
    }
}
```

---

## Tool Implementation

### `read_file(path: str) -> str`

**Logic:**
1. Resolve the path relative to project root
2. **Security check:** Ensure the resolved path is within the project directory (no `../` traversal)
3. Read file contents using `Path.read_text()`
4. Return contents as string, or error message if file doesn't exist

### `list_files(path: str) -> str`

**Logic:**
1. Resolve the path relative to project root
2. **Security check:** Ensure the resolved path is within the project directory
3. List directory entries using `Path.iterdir()`
4. Return newline-separated list of filenames (with `[DIR]` prefix for directories)

### Path Security

Both tools will use a `validate_path()` helper function:

```python
def validate_path(relative_path: str, project_root: Path) -> Path:
    """Validate that the path is within the project directory."""
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

---

## Agentic Loop

### Loop Structure

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question}
]
tool_calls_log = []
max_iterations = 10

for iteration in range(max_iterations):
    # 1. Call LLM with messages + tool definitions
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOL_DEFINITIONS,
        tool_choice="auto"
    )
    
    message = response.choices[0].message
    
    # 2. Check for tool calls
    if message.tool_calls:
        # Execute each tool and collect results
        for tool_call in message.tool_calls:
            result = execute_tool(tool_call, project_root)
            tool_calls_log.append({
                "tool": tool_call.function.name,
                "args": json.loads(tool_call.function.arguments),
                "result": result
            })
        
        # Append assistant message + tool results to messages
        messages.append(message)
        for tool_call in message.tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })
    else:
        # 3. No tool calls = final answer
        final_answer = message.content
        break
```

### Extracting Source

The system prompt will instruct the LLM to include source references in a structured format. I will use a regex or parsing logic to extract:
- The answer text
- The source file path + section anchor (e.g., `wiki/git-workflow.md#resolving-merge-conflicts`)

**Strategy:** Include in the system prompt:
> "After finding the answer, output it in this format:\n\nANSWER: <your answer>\nSOURCE: <file_path>#<section_anchor>"

Then parse the response to extract these fields.

---

## System Prompt Strategy

The system prompt will:

1. **Define the agent's role:** "You are a documentation assistant that answers questions by reading files from the project wiki."

2. **Describe available tools:** Explain when to use `list_files` vs `read_file`

3. **Provide workflow guidance:**
   - First use `list_files` to discover relevant wiki files
   - Then use `read_file` to read specific files
   - Extract the answer and identify the exact section

4. **Specify output format:** Require the LLM to output answer + source in a parseable format

5. **Set constraints:** Maximum 10 tool calls, be concise, cite sources accurately

---

## Output Format

```json
{
    "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
    "source": "wiki/git-workflow.md#merge-the-pr",
    "tool_calls": [
        {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
        {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
    ]
}
```

---

## Testing Strategy

### Test 1: `read_file` usage
**Question:** "How do you resolve a merge conflict?"
**Expected:**
- `tool_calls` contains at least one `read_file` call
- `source` contains `wiki/git-workflow.md`

### Test 2: `list_files` usage
**Question:** "What files are in the wiki?"
**Expected:**
- `tool_calls` contains at least one `list_files` call with `path: "wiki"`

---

## Implementation Steps

1. ✅ Create this plan file
2. Add tool helper functions (`read_file_tool`, `list_files_tool`, `validate_path`)
3. Add tool definitions for LLM
4. Implement the agentic loop in `get_answer()`
5. Add source extraction logic
6. Update output JSON to include `source` and `tool_calls`
7. Update `AGENT.md` documentation
8. Write 2 regression tests
9. Test manually with sample questions
10. Run all tests and verify

---

## Error Handling

| Error | Behavior |
|-------|----------|
| Path traversal attempt | Return error message to LLM |
| File not found | Return error message to LLM |
| Directory not found | Return error message to LLM |
| LLM returns no answer | Return empty answer with tool_calls log |
| Max iterations reached | Return partial answer with all tool_calls |
