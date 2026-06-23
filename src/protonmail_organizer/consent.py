"""One-time, persisted risk acknowledgments.

This tool reaches ProtonMail through an unofficial, reverse-engineered API and
can send email content to a third-party AI provider. Both carry risks the user
should accept explicitly. Acknowledgments are stored under the config directory
so each prompt appears only the first time.

Set ``PMO_ACCEPT_RISKS=1`` to accept every acknowledgment non-interactively
(useful for scripts and CI). This is an explicit opt-in, never the default.
"""

from __future__ import annotations

import json
import os
import sys

import click

from .config import CONFIG_DIR, ensure_config_dir
from .display import console

CONSENT_FILE = CONFIG_DIR / "consent.json"

# Environment variable that accepts all acknowledgments without prompting.
ACCEPT_ENV = "PMO_ACCEPT_RISKS"

# Acknowledgment keys.
UNOFFICIAL_USE = "unofficial_use"
AI_EGRESS = "ai_egress"

_UNOFFICIAL_DETAILS = (
    "[bold yellow]⚠  Unofficial ProtonMail access[/bold yellow]\n"
    "This tool talks to ProtonMail through an unofficial, reverse-engineered API\n"
    "(protonmail-api-client). Proton provides no public API, and automated access\n"
    "may violate Proton's Terms of Service. Your account could be rate-limited,\n"
    "flagged, or locked, and the private API may change at any time and break this\n"
    "tool without warning. Always preview destructive actions with --dry-run first."
)

_AI_DETAILS = (
    "[bold yellow]⚠  Email content leaves your device[/bold yellow]\n"
    "Drafting AI replies sends the body of the email you are replying to — plus\n"
    "truncated snippets of your sent mail (your writing-style profile) — to the\n"
    "Anthropic API for processing. Do not use this on confidential mail you do not\n"
    "want shared with a third-party AI provider."
)


def _is_interactive() -> bool:
    """Return True if we can prompt the user (stdin is a terminal)."""
    try:
        return sys.stdin.isatty()
    except (ValueError, AttributeError):
        return False


def _load() -> dict:
    try:
        with open(CONSENT_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    ensure_config_dir()
    with open(CONSENT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(CONSENT_FILE, 0o600)
    except OSError:
        pass


def has_consent(key: str) -> bool:
    """Return True if the user has already acknowledged ``key``."""
    return bool(_load().get(key))


def record_consent(key: str) -> None:
    """Persist acknowledgment for ``key``."""
    data = _load()
    data[key] = True
    _save(data)


def require_consent(key: str, details: str, prompt: str) -> bool:
    """Ensure a one-time acknowledgment for ``key``.

    Returns True if granted (now or previously), or False if declined or no
    confirmation can be obtained. Honors ``PMO_ACCEPT_RISKS=1``.
    """
    if has_consent(key):
        return True

    console.print(details)

    if os.environ.get(ACCEPT_ENV) == "1":
        console.print(f"[dim]{ACCEPT_ENV}=1 set — acknowledgment recorded.[/dim]")
        record_consent(key)
        return True

    if not _is_interactive():
        console.print(
            "[red]Cannot prompt for confirmation (no interactive terminal).[/red] "
            f"Re-run interactively, or set {ACCEPT_ENV}=1 to accept."
        )
        return False

    if click.confirm(prompt, default=False):
        record_consent(key)
        return True

    console.print("[yellow]Not acknowledged — aborting.[/yellow]")
    return False


def require_unofficial_use_ack() -> bool:
    """One-time acknowledgment that this is unofficial, ToS-risky access."""
    return require_consent(
        UNOFFICIAL_USE,
        _UNOFFICIAL_DETAILS,
        "I understand the risks and want to continue",
    )


def require_ai_egress_ack() -> bool:
    """One-time acknowledgment that email content is sent to Anthropic."""
    return require_consent(
        AI_EGRESS,
        _AI_DETAILS,
        "Send email content to Anthropic to draft replies",
    )
