"""Configuration directory and file management."""

import os
from pathlib import Path


CONFIG_DIR = Path(os.environ.get(
    "PMO_CONFIG_DIR",
    os.path.expanduser("~/.config/protonmail-organizer"),
))

SESSION_FILE = CONFIG_DIR / "session.dat"
RULES_FILE = CONFIG_DIR / "rules.yaml"
STYLE_PROFILE_FILE = CONFIG_DIR / "style_profile.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def ensure_config_dir() -> Path:
    """Create config directory if it doesn't exist. Returns the path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR
