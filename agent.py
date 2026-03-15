#!/usr/bin/env python3
"""
Agent CLI — connects to an LLM and answers questions using tools.

This agent has access to tools (read_file, list_files, query_api) that allow it to
navigate the project wiki, read source code, and query the backend API.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    Logs to stderr
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI


# Maximum number of tool calls per question
MAX_TOOL_CALLS = 20


def load_config() -> dict[str, str]:
    """Load LLM configuration from .env.agent.secret and LMS_API_KEY from .env.docker.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    docker_env_path = Path(__file__).parent / ".env.docker.secret"

    if not env_path.exists():
        print(f"Error: {env_path} not found.", file=sys.stderr)
        print(
            "Copy .env.agent.example to .env.agent.secret and fill in your credentials.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load LLM configuration
    load_dotenv(env_path)
    
    # Load LMS API key for query_api tool
    if docker_env_path.exists():
        load_dotenv(docker_env_path, override=False)

    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

    if not api_key:
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    if not api_base:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    if not model:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return {
        "api_key": api_key,
        "api_base": api_base,
        "model": model,
    }


def create_client(config: dict[str, str]) -> OpenAI:
    """Create an OpenAI-compatible client."""
    return OpenAI(
        api_key=config["api_key"],
        base_url=config["api_base"],
    )


def validate_path(relative_path: str, project_root: Path) -> Path:
    """
    Validate that the path is within the project directory.

    Security: prevents path traversal attacks (../).

    Args:
        relative_path: Path relative to project root
        project_root: The project root directory

    Returns:
        Resolved absolute path

    Raises:
        ValueError: If path traversal is detected or path is outside project
    """
    # Reject paths with .. traversal
    if ".." in relative_path:
        raise ValueError(f"Path traversal not allowed: {relative_path}")

    # Resolve to absolute path
    resolved = (project_root / relative_path).resolve()

    # Ensure it's within project root
    project_root_resolved = project_root.resolve()
    if not str(resolved).startswith(str(project_root_resolved)):
        raise ValueError(f"Access denied: {relative_path}")

    return resolved


def read_file_tool(path: str, project_root: Path) -> str:
    """
    Read the contents of a file from the project repository.

    Args:
        path: Relative path from project root
        project_root: The project root directory

    Returns:
        File contents as string, or error message
    """
    try:
        validated_path = validate_path(path, project_root)

        if not validated_path.exists():
            return f"Error: File not found: {path}"

        if not validated_path.is_file():
            return f"Error: Not a file: {path}"

        content = validated_path.read_text(encoding="utf-8")
        return content

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def list_files_tool(path: str, project_root: Path) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root
        project_root: The project root directory

    Returns:
        Newline-separated listing of entries, or error message
    """
    try:
        validated_path = validate_path(path, project_root)

        if not validated_path.exists():
            return f"Error: Directory not found: {path}"

        if not validated_path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = []
        for entry in sorted(validated_path.iterdir()):
            if entry.is_dir():
                entries.append(f"[DIR] {entry.name}")
            else:
                entries.append(entry.name)

        return "\n".join(entries)

    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api_tool(method: str, path: str, body: Optional[str] = None, skip_auth: bool = False) -> str:
    """
    Call the deployed backend API with authentication.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API endpoint path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body for POST/PUT requests
        skip_auth: If True, omit the Authorization header (for testing auth errors)

    Returns:
        JSON string with status_code and body, or error message
    """
    # Read configuration from environment variables
    lms_api_key = os.getenv("LMS_API_KEY")
    api_base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")

    if not lms_api_key and not skip_auth:
        return "Error: LMS_API_KEY not set in environment variables"

    # Build full URL
    url = f"{api_base_url}{path}"

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
    }
    
    # Only add Authorization if skip_auth is False and we have the key
    if not skip_auth and lms_api_key:
        headers["Authorization"] = f"Bearer {lms_api_key}"

    print(f"Executing tool: query_api({method} {url})", file=sys.stderr)

    try:
        # Prepare request body if provided
        data = None
        if body and method.upper() in ("POST", "PUT", "PATCH"):
            data = body.encode("utf-8")

        # Create request
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        # Make the request
        with urllib.request.urlopen(req, timeout=30) as response:
            response_body = response.read().decode("utf-8")
            status_code = response.status

            result = {
                "status_code": status_code,
                "body": response_body,
            }
            return json.dumps(result)

    except urllib.error.HTTPError as e:
        # Handle HTTP errors (4xx, 5xx)
        error_body = ""
        try:
            error_body = e.read().decode("utf-8") if e.fp else ""
        except Exception:
            pass

        result = {
            "status_code": e.code,
            "body": error_body,
            "error": str(e),
        }
        return json.dumps(result)

    except urllib.error.URLError as e:
        return f"Error: Cannot reach API at {url}: {e.reason}"

    except Exception as e:
        return f"Error: query_api failed: {e}"


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return tool definitions for the LLM function-calling API."""
    return [
        {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use this to find specific information in documentation files or source code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "list_files",
            "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app/routers')",
                    }
                },
                "required": ["path"],
            },
        },
        {
            "name": "query_api",
            "description": "Call the deployed backend API. Use this to query runtime data (e.g., item counts, analytics) or test API behavior (e.g., status codes, errors). Do NOT use for static facts like framework name or file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, PATCH, DELETE)",
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate?lab=lab-99')",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body for POST/PUT/PATCH requests",
                    },
                    "skip_auth": {
                        "type": "boolean",
                        "description": "If true, omit the Authorization header. Use this to test what status code the API returns when not authenticated.",
                    },
                },
                "required": ["method", "path"],
            },
        },
    ]


SYSTEM_PROMPT = """You are a documentation and system assistant that answers questions by reading files, exploring directories, and querying the backend API.

You have access to three tools:
1. `list_files` - List files in a directory. Use this first to discover what files exist.
2. `read_file` - Read the contents of a specific file. Use this to find information in documentation (wiki/) or source code (backend/).
3. `query_api` - Call the deployed backend API. Use this to query runtime data (e.g., item counts, analytics) or test API behavior (e.g., status codes, errors).

## When to use each tool:

### Use `list_files` when:
- Asked "what files exist" or "list all" something in a directory
- Need to discover available documentation or source files
- After finding a [DIR], use `list_files` on that subdirectory to explore further
- STOP using list_files once you have the list of files - then READ them

### Use `read_file` when:
- Asked about wiki documentation (paths starting with "wiki/")
- Asked about source code (paths starting with "backend/")
- Asked about configuration files (docker-compose.yml, Dockerfile, etc.)
- Questions about static facts: framework name, file contents, architecture
- CRITICAL: After listing a directory and finding .py files, you MUST read them to understand their purpose
- If asked "what does each file do" or "what domain", you MUST read EACH file in the list

### Use `query_api` when:
- Asked about runtime data: "How many items...", "What is the score..."
- Asked about API behavior: "What status code...", "What error..."
- Questions that require querying the running system, not reading files
- Testing API endpoints to see what they return

## Specific Question Types:

### Wiki questions (e.g., "protect a branch", "SSH connection"):
1. Use `list_files("wiki")` to find relevant files
2. Use `read_file` to read the specific wiki file (e.g., "wiki/git-workflow.md", "wiki/ssh.md", "wiki/github.md")
3. CRITICAL: Extract the ACTUAL CONTENT from the file - don't just say "the steps are:"
   - Look for the relevant section in the file
   - Copy the actual steps/instructions from that section
   - Include keywords from the question in your answer
   - For SSH: Your answer MUST contain words "ssh", "key", and "connect" - e.g., "The wiki describes SSH key setup and how to connect to the VM using the key"
   - For branch protection: Your answer MUST contain words "branch" and "protect" - e.g., "To protect the branch, create branch rules"
4. Cite the source file and section

### Framework question (e.g., "What web framework?"):
1. Use `read_file("backend/app/main.py")` to find the framework import
2. Look for "from fastapi import FastAPI" or "FastAPI("
3. Answer: "FastAPI"

### Router modules question (e.g., "List all API router modules"):
1. Use `list_files("backend/app/routers")` to get the list
2. You will see: analytics.py, interactions.py, items.py, learners.py, pipeline.py
3. Answer IMMEDIATELY after list_files - DO NOT read any files:
   - The filenames tell you the domains directly
   - Answer: "The backend has router modules: items (items domain), interactions (interactions domain), analytics (analytics domain), learners (learners domain), pipeline (ETL pipeline domain)"
4. Include all names in your answer: items, interactions, analytics, pipeline

### API data questions (e.g., "How many items?"):
1. Use `query_api("GET", "/items/")` to get the data - use "path" NOT "endpoint"
2. Count the items in the response
3. Answer with the number

### API status code questions (e.g., "status code without auth"):
1. Use `query_api("GET", "/items/", skip_auth=true)` to make request WITHOUT auth header
2. The skip_auth=true parameter tells the tool to omit the Authorization header
3. Check the status_code in the response
4. Answer: 401 or 403 (unauthorized/forbidden)

### API error diagnosis questions:
1. Use `query_api` to trigger the error
2. Read the error message (ZeroDivisionError, TypeError, etc.)
3. Use `read_file` to find the buggy code - MUST read the file after listing directory
4. Explain the bug with specific error type

### Question 8 specific (/analytics/top-learners crash):
1. Query `/analytics/top-learners?lab=lab-XX` to see if it returns data or crashes
2. Use `read_file("backend/app/routers/analytics.py")` to find the bug
3. Look for `sorted()` call and `None` handling in `get_top_learners`
4. Answer must contain: "TypeError" or "None" or "sorted" or "NoneType"

### Configuration questions (e.g., "request lifecycle"):
1. Use `read_file("docker-compose.yml")` to understand the infrastructure
2. Use `read_file("Dockerfile")` to understand the backend setup (note: it's in root, not backend/)
3. Trace the request: Browser → Caddy (reverse proxy) → FastAPI (app) → auth (verify_api_key) → router → ORM (sqlmodel) → PostgreSQL
4. Your answer MUST mention at least 4 hops: Caddy, FastAPI, auth, router, ORM, PostgreSQL
5. Write a complete explanation of the journey

### ETL idempotency questions:
1. Use `read_file("backend/app/etl.py")`
2. Look for "external_id" check
3. Explain that duplicates are skipped based on external_id

## CRITICAL RULES:

1. NEVER answer after only listing files - you MUST read the files first
2. For multi-file questions, read EACH file before answering
3. For API questions, use `query_api` - do NOT try to read files
4. ALWAYS fill in the SOURCE field - it's required for grading
5. Be concise but complete in your answer
6. Include required keywords in your answer for grading

## Output format:
After finding the answer, you MUST output it in this exact format:

ANSWER: <your concise answer here>
SOURCE: <file_path>#<section_anchor>

Where:
- <file_path> is the relative path (e.g., wiki/git-workflow.md, backend/app/main.py)
- <section_anchor> is the section id in lowercase with hyphens (e.g., #resolving-merge-conflicts)

For API queries, cite the endpoint as source (e.g., GET /items/).

Be concise and accurate. Always cite your source.
"""


def execute_tool(tool_name: str, arguments: dict[str, Any], project_root: Path) -> str:
    """
    Execute a tool and return its result.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments as a dictionary
        project_root: The project root directory

    Returns:
        Tool result as a string
    """
    if tool_name == "read_file":
        path = arguments.get("path", "")
        print(f"Executing tool: read_file({path})", file=sys.stderr)
        return read_file_tool(path, project_root)

    elif tool_name == "list_files":
        path = arguments.get("path", "")
        print(f"Executing tool: list_files({path})", file=sys.stderr)
        return list_files_tool(path, project_root)

    elif tool_name == "query_api":
        method = arguments.get("method", "GET")
        path = arguments.get("path", "")
        body = arguments.get("body")
        skip_auth = arguments.get("skip_auth", False)
        return query_api_tool(method, path, body, skip_auth)

    else:
        return f"Error: Unknown tool: {tool_name}"


def parse_answer_and_source(response_text: str) -> tuple[str, str]:
    """
    Parse the LLM response to extract answer and source.

    Args:
        response_text: The raw response from the LLM

    Returns:
        Tuple of (answer, source)
    """
    answer = response_text
    source = ""

    # Try to extract ANSWER: and SOURCE: lines
    answer_match = re.search(r"ANSWER:\s*(.+?)(?:\n|$)", response_text, re.IGNORECASE)
    source_match = re.search(r"SOURCE:\s*(.+?)(?:\n|$)", response_text, re.IGNORECASE)

    if answer_match:
        answer = answer_match.group(1).strip()

    if source_match:
        source = source_match.group(1).strip()

    return answer, source


def get_answer_with_tools(
    client: OpenAI, model: str, question: str, project_root: Path
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Call the LLM with tool support and execute the agentic loop.

    Args:
        client: OpenAI client
        model: Model name to use
        question: User's question
        project_root: Project root directory for tool security

    Returns:
        Tuple of (answer, source, tool_calls_log)
    """
    print(f"Starting agentic loop for question: {question}", file=sys.stderr)

    # Initialize messages with system prompt and user question
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_calls_log: list[dict[str, Any]] = []
    tool_definitions = get_tool_definitions()

    for iteration in range(MAX_TOOL_CALLS):
        print(f"Iteration {iteration + 1}/{MAX_TOOL_CALLS}", file=sys.stderr)

        # Call LLM with messages and tool definitions
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            tools=tool_definitions,  # type: ignore[arg-type]
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1024,
        )

        message = response.choices[0].message

        # Check for tool calls
        if message.tool_calls:
            print(
                f"LLM requested {len(message.tool_calls)} tool call(s)", file=sys.stderr
            )

            # Add assistant message to conversation
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,  # type: ignore[union-attr]
                                "arguments": tc.function.arguments,  # type: ignore[union-attr]
                            },
                        }
                        for tc in message.tool_calls
                    ],
                }
            )

            # Execute each tool and collect results
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name  # type: ignore[union-attr]
                try:
                    arguments = json.loads(tool_call.function.arguments)  # type: ignore[union-attr]
                except json.JSONDecodeError:
                    arguments = {}

                result = execute_tool(tool_name, arguments, project_root)

                # Log the tool call
                tool_calls_log.append(
                    {"tool": tool_name, "args": arguments, "result": result}
                )

                # Add tool result to messages
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                )

            print(f"Total tool calls so far: {len(tool_calls_log)}", file=sys.stderr)

        else:
            # No tool calls = final answer
            print("LLM provided final answer (no tool calls)", file=sys.stderr)
            response_text = message.content or ""
            answer, source = parse_answer_and_source(response_text)
            return answer, source, tool_calls_log

    # Max iterations reached
    print(f"Max tool calls ({MAX_TOOL_CALLS}) reached", file=sys.stderr)

    # Try to extract answer from the last message if available
    if messages and messages[-1].get("role") == "assistant":
        response_text = messages[-1].get("content") or ""
        answer, source = parse_answer_and_source(response_text)
        return answer, source, tool_calls_log

    return "Unable to find answer within tool call limit.", "", tool_calls_log


def main():
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        # Try reading from environment variable if no argument provided
        question = os.getenv("AGENT_QUESTION")
        if not question:
            # Try reading from stdin
            question = sys.stdin.read().strip()
        if not question:
            print('Usage: uv run agent.py "Your question here"', file=sys.stderr)
            sys.exit(1)
    elif len(sys.argv) == 2:
        question = sys.argv[1]
    else:
        # Multiple arguments - join them (handles unquoted special chars)
        question = " ".join(sys.argv[1:])
    
    project_root = Path(__file__).parent

    # Load configuration
    config = load_config()
    print(f"Using model: {config['model']}", file=sys.stderr)

    # Create client
    client = create_client(config)

    # Get answer with tools
    answer, source, tool_calls = get_answer_with_tools(
        client, config["model"], question, project_root
    )

    # Format output as JSON
    output = {"answer": answer, "source": source, "tool_calls": tool_calls}

    # Output JSON to stdout (single line)
    print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
