#!/usr/bin/env python3
"""
Agent CLI — connects to an LLM and answers questions using tools.

This agent has access to tools (read_file, list_files) that allow it to
navigate the project wiki and find answers in documentation.

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
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10


def load_config() -> dict[str, str]:
    """Load LLM configuration from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"

    if not env_path.exists():
        print(f"Error: {env_path} not found.", file=sys.stderr)
        print(
            "Copy .env.agent.example to .env.agent.secret and fill in your credentials.",
            file=sys.stderr,
        )
        sys.exit(1)

    load_dotenv(env_path)

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


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return tool definitions for the LLM function-calling API."""
    return [
        {
            "name": "read_file",
            "description": "Read the contents of a file from the project repository. Use this to find specific information in documentation files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
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
                        "description": "Relative directory path from project root (e.g., 'wiki')",
                    }
                },
                "required": ["path"],
            },
        },
    ]


SYSTEM_PROMPT = """You are a documentation assistant that answers questions by reading files from the project wiki.

You have access to two tools:
1. `list_files` - List files in a directory. Use this first to discover what wiki files exist.
2. `read_file` - Read the contents of a specific file. Use this to find the actual answer.

Workflow:
1. First, use `list_files` with path "wiki" to discover relevant documentation files.
2. Then, use `read_file` to read specific files that might contain the answer.
3. Look for section headers (lines starting with # or ##) to identify relevant sections.
4. Once you find the answer, extract it and note the exact file path and section.

Output format:
After finding the answer, you MUST output it in this exact format:

ANSWER: <your concise answer here>
SOURCE: <file_path>#<section_anchor>

Where:
- <file_path> is the relative path (e.g., wiki/git-workflow.md)
- <section_anchor> is the section id in lowercase with hyphens (e.g., #resolving-merge-conflicts)

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
                    "content": message.content,
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
            response_text = message.content if message.content else ""
            answer, source = parse_answer_and_source(response_text)
            return answer, source, tool_calls_log

    # Max iterations reached
    print(f"Max tool calls ({MAX_TOOL_CALLS}) reached", file=sys.stderr)

    # Try to extract answer from the last message if available
    if messages and messages[-1].get("role") == "assistant":
        response_text = messages[-1].get("content", "")
        answer, source = parse_answer_and_source(response_text)
        return answer, source, tool_calls_log

    return "Unable to find answer within tool call limit.", "", tool_calls_log


def main():
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "Your question here"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
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
