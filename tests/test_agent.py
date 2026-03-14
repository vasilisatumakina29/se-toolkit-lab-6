"""Regression tests for agent.py CLI.

These tests verify that agent.py:
1. Runs successfully with a question argument
2. Outputs valid JSON to stdout
3. Contains required fields: answer and tool_calls
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_outputs_valid_json():
    """Test that agent.py outputs valid JSON with required fields."""
    # Path to agent.py in project root
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"
    
    # Test question
    question = "What is 2 + 2?"
    
    # Run agent.py as subprocess
    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=60,
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
    
    # Verify required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    
    # Verify field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"
    
    # Verify answer is non-empty
    assert output["answer"].strip(), "'answer' field is empty"
    
    print("All checks passed!", file=sys.stderr)
