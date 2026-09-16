"""Configuration directory and file management."""

import os
from pathlib import Path

CONFIG_DIR = Path(
    os.environ.get(
        "PMO_CONFIG_DIR",
        os.path.expanduser("~/.config/protonmail-organizer"),
    )
)

SESSION_FILE = CONFIG_DIR / "session.dat"
RULES_FILE = CONFIG_DIR / "rules.yaml"
STYLE_PROFILE_FILE = CONFIG_DIR / "style_profile.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# AI backend for draft replies: "anthropic" (cloud, default) or "local" — any
# OpenAI-compatible server (Ollama, LM Studio, llama.cpp, vLLM, …). A local
# backend on localhost keeps email content on your machine (no third-party API).
AI_BACKEND = os.environ.get("PMO_AI_BACKEND", "anthropic")

# Model id. When unset, each backend falls back to its own default below.
AI_MODEL = os.environ.get("PMO_AI_MODEL", "")
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
DEFAULT_LOCAL_MODEL = "llama3.1"

# Local / OpenAI-compatible connection. The default targets Ollama's
# OpenAI-compatible endpoint. PMO_AI_API_KEY is optional — most local servers
# ignore it; set it only for gateways that require a bearer token.
AI_BASE_URL = os.environ.get("PMO_AI_BASE_URL", "http://localhost:11434/v1")
AI_API_KEY = os.environ.get("PMO_AI_API_KEY", "")

# Backwards-compatible alias for the previous single-model knob.
ANTHROPIC_MODEL = AI_MODEL or DEFAULT_ANTHROPIC_MODEL


def ensure_config_dir() -> Path:
    """Create config directory if it doesn't exist. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def write_private(path: Path, text: str) -> None:
    """Write text to a file that is owner-only (0o600) from the moment it exists.

    Unlike write-then-chmod, the file is never world-readable, even briefly.
    Files created earlier with looser permissions are tightened too.
    """

    def _opener(p, flags):
        return os.open(p, flags, 0o600)

    with open(path, "w", opener=_opener) as f:
        f.write(text)
    os.chmod(path, 0o600)
