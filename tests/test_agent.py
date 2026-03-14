"""Regression tests for agent.py CLI.

These tests verify that agent.py:
1. Runs successfully with a question argument
2. Outputs valid JSON to stdout
3. Contains required fields: answer, source, and tool_calls
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_agent(question: str, project_root: Path, timeout: int = 120) -> dict[str, Any]:
    """Helper function to run agent.py and parse JSON output."""
    agent_path = project_root / "agent.py"

    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # Check exit code
    assert result.returncode == 0, f"agent.py failed with: {result.stderr}"

    # Parse stdout as JSON
    stdout = result.stdout.strip()
    assert stdout, "stdout is empty"

    try:
        output = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"stdout is not valid JSON: {e}\nstdout: {stdout}")

    return output


def test_agent_outputs_valid_json():
    """Test that agent.py outputs valid JSON with required fields."""
    # Path to agent.py in project root
    project_root = Path(__file__).parent.parent

    # Test question
    question = "What is 2 + 2?"

    output = run_agent(question, project_root)

    # Verify required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert "source" in output, "Missing 'source' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Verify field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert isinstance(output["source"], str), "'source' must be a string"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"

    # Verify answer is non-empty
    assert output["answer"].strip(), "'answer' field is empty"

    print("All checks passed!", file=sys.stderr)


def test_agent_uses_read_file_for_wiki_question():
    """Test that agent uses read_file tool when answering wiki questions.

    Question: "How do you resolve a merge conflict?"
    Expected:
    - tool_calls contains at least one read_file call
    - source contains wiki/git-workflow.md
    """
    project_root = Path(__file__).parent.parent
    question = "How do you resolve a merge conflict?"

    output = run_agent(question, project_root)

    # Verify tool_calls contains read_file
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )

    # Verify source contains wiki/git-workflow.md
    assert "wiki/git-workflow.md" in output["source"], (
        f"Expected 'wiki/git-workflow.md' in source, got: {output['source']}"
    )

    # Verify answer is non-empty
    assert output["answer"].strip(), "'answer' field is empty"

    print(f"read_file test passed! Source: {output['source']}", file=sys.stderr)


def test_agent_uses_list_files_for_directory_question():
    """Test that agent uses list_files tool when asked about directory contents.

    Question: "What files are in the wiki?"
    Expected:
    - tool_calls contains at least one list_files call with path "wiki"
    """
    project_root = Path(__file__).parent.parent
    question = "What files are in the wiki?"

    output = run_agent(question, project_root)

    # Verify tool_calls contains list_files
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "list_files" in tool_names, (
        f"Expected 'list_files' in tool_calls, got: {tool_names}"
    )

    # Verify list_files was called with path "wiki"
    list_files_calls = [
        tc for tc in output["tool_calls"] if tc.get("tool") == "list_files"
    ]
    wiki_path_found = any(
        tc.get("args", {}).get("path") == "wiki" for tc in list_files_calls
    )
    assert wiki_path_found, (
        f"Expected list_files to be called with path 'wiki', "
        f"got args: {[tc.get('args') for tc in list_files_calls]}"
    )

    # Verify answer is non-empty
    assert output["answer"].strip(), "'answer' field is empty"

    print(
        f"list_files test passed! Found {len(output['tool_calls'])} tool call(s)",
        file=sys.stderr,
    )
