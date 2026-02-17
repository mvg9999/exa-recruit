"""Configuration loading for exa-recruit."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def find_env_file() -> Path | None:
    """Find .env file by walking up from CWD or using package location."""
    # Check CWD first
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
    # Check package root
    pkg_env = Path(__file__).parent.parent.parent / ".env"
    if pkg_env.exists():
        return pkg_env
    return None


def get_api_key() -> str:
    """Load and return the Exa API key."""
    env_file = find_env_file()
    if env_file:
        load_dotenv(env_file)

    key = os.environ.get("EXA_API_KEY", "")
    if not key:
        print("Error: EXA_API_KEY not found. Set it in .env or as an environment variable.", file=sys.stderr)
        raise SystemExit(2)
    return key


def get_anthropic_key() -> str:
    """Load and return the Anthropic API key for LLM filtering."""
    env_file = find_env_file()
    if env_file:
        load_dotenv(env_file)

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("Error: ANTHROPIC_API_KEY not found. Set it in .env or as an environment variable.", file=sys.stderr)
        print("This key is required for LLM-based candidate filtering.", file=sys.stderr)
        raise SystemExit(2)
    return key
