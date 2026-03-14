#!/usr/bin/env python3
"""
Agent CLI — connects to an LLM and answers questions.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    Logs to stderr
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def load_config() -> dict:
    """Load LLM configuration from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    
    if not env_path.exists():
        print(f"Error: {env_path} not found.", file=sys.stderr)
        print("Copy .env.agent.example to .env.agent.secret and fill in your credentials.", file=sys.stderr)
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


def create_client(config: dict) -> OpenAI:
    """Create an OpenAI-compatible client."""
    return OpenAI(
        api_key=config["api_key"],
        base_url=config["api_base"],
    )


def get_answer(client: OpenAI, model: str, question: str) -> str:
    """Call the LLM and get an answer."""
    print(f"Sending question to LLM: {question}", file=sys.stderr)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant. Answer questions concisely and accurately."
            },
            {
                "role": "user",
                "content": question
            }
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    
    answer = response.choices[0].message.content
    print(f"Received answer from LLM", file=sys.stderr)
    
    return answer if answer else ""


def main():
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        sys.exit(1)
    
    question = sys.argv[1]
    
    # Load configuration
    config = load_config()
    print(f"Using model: {config['model']}", file=sys.stderr)
    
    # Create client and get answer
    client = create_client(config)
    answer = get_answer(client, config["model"], question)
    
    # Format output as JSON
    output = {
        "answer": answer,
        "tool_calls": []
    }
    
    # Output JSON to stdout (single line)
    print(json.dumps(output))
    
    sys.exit(0)


if __name__ == "__main__":
    main()
