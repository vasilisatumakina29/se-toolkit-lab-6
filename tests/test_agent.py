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
        [sys.executable, str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=project_root,
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
    - answer is non-empty
    """
    project_root = Path(__file__).parent.parent
    question = "How do you resolve a merge conflict?"

    output = run_agent(question, project_root)

    # Verify tool_calls contains read_file
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )

    # Verify answer is non-empty
    assert output["answer"].strip(), "'answer' field is empty"

    print(f"read_file wiki test passed! Source: {output['source']}", file=sys.stderr)


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


def test_agent_uses_read_file_for_framework_question():
    """Test that agent uses read_file tool when asked about the backend framework.

    Question: "What framework does the backend use?"
    Expected:
    - tool_calls contains at least one read_file call
    - answer is non-empty (actual content depends on LLM)
    """
    project_root = Path(__file__).parent.parent
    question = "What Python web framework does this project's backend use?"

    output = run_agent(question, project_root)

    # Verify tool_calls contains read_file
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "read_file" in tool_names, (
        f"Expected 'read_file' in tool_calls, got: {tool_names}"
    )

    # Verify source points to backend file
    assert "backend" in output["source"].lower() or "main.py" in output["source"].lower() or "pyproject" in output["source"].lower(), (
        f"Expected source to reference backend file, got: {output['source']}"
    )

    # Verify answer is non-empty
    assert output["answer"].strip(), "'answer' field is empty"

    print(
        f"read_file framework test passed! Source: {output['source']}",
        file=sys.stderr,
    )


def test_agent_uses_query_api_for_data_question():
    """Test that agent uses query_api tool when asked about runtime data.

    Question: "How many items are in the database?"
    Expected:
    - tool_calls contains at least one query_api call
    - query_api is called with GET method and /items/ path (or endpoint)
    - answer is non-empty (may contain error if API not running)
    """
    project_root = Path(__file__).parent.parent
    question = "How many items are currently stored in the database?"

    output = run_agent(question, project_root)

    # Verify tool_calls contains query_api
    tool_names = [tc.get("tool") for tc in output["tool_calls"]]
    assert "query_api" in tool_names, (
        f"Expected 'query_api' in tool_calls, got: {tool_names}"
    )

    # Verify query_api was called with GET method and /items/ path
    query_api_calls = [
        tc for tc in output["tool_calls"] if tc.get("tool") == "query_api"
    ]
    # Check both 'path' and 'endpoint' keys (model may use either)
    items_path_found = any(
        tc.get("args", {}).get("path") == "/items/" or
        tc.get("args", {}).get("endpoint") == "/items/"
        for tc in query_api_calls
    )
    assert items_path_found, (
        f"Expected query_api to be called with path '/items/', "
        f"got args: {[tc.get('args') for tc in query_api_calls]}"
    )

    # Verify answer is non-empty (may contain error if API not running)
    assert output["answer"].strip(), "'answer' field is empty"

    print(
        f"query_api test passed! Found {len(query_api_calls)} query_api call(s)",
        file=sys.stderr,
    )
