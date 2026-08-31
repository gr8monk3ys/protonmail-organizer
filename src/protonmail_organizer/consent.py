"""One-time, persisted risk acknowledgments.

This tool reaches ProtonMail through an unofficial, reverse-engineered API and
can send email content to a third-party AI provider. Both carry risks the user
should accept explicitly. Acknowledgments are stored under the config directory
so each prompt appears only the first time.

Set ``PMO_ACCEPT_RISKS=1`` to accept the unofficial-API acknowledgment
non-interactively (useful for scripts and CI). Sending mail content to an AI
provider is a separate decision with its own opt-in,
``PMO_ACCEPT_AI_EGRESS=1`` — so scripted cleanup never silently authorizes
data egress. Both are explicit opt-ins, never the default.
"""

from __future__ import annotations

import json
import os
import sys

import click

from .config import CONFIG_DIR, ensure_config_dir, write_private
from .display import console

CONSENT_FILE = CONFIG_DIR / "consent.json"

# Environment variables that accept acknowledgments without prompting.
# Deliberately separate: accepting unofficial-API risk for scripting must not
# also pre-authorize sending mail content to an AI provider.
ACCEPT_ENV = "PMO_ACCEPT_RISKS"
AI_EGRESS_ENV = "PMO_ACCEPT_AI_EGRESS"

# Acknowledgment keys.
UNOFFICIAL_USE = "unofficial_use"
AI_EGRESS = "ai_egress"

# The destination the legacy AI_EGRESS key was worded for.
ANTHROPIC_HOST = "api.anthropic.com"

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
    "truncated snippets of your sent mail (your writing-style profile) — to\n"
    "[bold]{destination}[/bold] for processing. Do not use this on confidential\n"
    "mail you do not want shared with that provider."
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
    write_private(CONSENT_FILE, json.dumps(data, indent=2))


def has_consent(key: str) -> bool:
    """Return True if the user has already acknowledged ``key``."""
    return bool(_load().get(key))


def record_consent(key: str) -> None:
    """Persist acknowledgment for ``key``."""
    data = _load()
    data[key] = True
    _save(data)


def require_consent(key: str, details: str, prompt: str, accept_env: str = ACCEPT_ENV) -> bool:
    """Ensure a one-time acknowledgment for ``key``.

    Returns True if granted (now or previously), or False if declined or no
    confirmation can be obtained. ``accept_env`` names the environment
    variable that accepts this acknowledgment non-interactively.
    """
    if has_consent(key):
        return True

    console.print(details)

    if os.environ.get(accept_env) == "1":
        console.print(f"[dim]{accept_env}=1 set — acknowledgment recorded.[/dim]")
        record_consent(key)
        return True

    if not _is_interactive():
        console.print(
            "[red]Cannot prompt for confirmation (no interactive terminal).[/red] "
            f"Re-run interactively, or set {accept_env}=1 to accept."
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


def require_ai_egress_ack(destination_host: str = ANTHROPIC_HOST) -> bool:
    """One-time acknowledgment that email content is sent to ``destination_host``.

    Consent is keyed per destination: acknowledging one provider never covers
    another. Uses its own env opt-in (PMO_ACCEPT_AI_EGRESS), separate from
    PMO_ACCEPT_RISKS.
    """
    key = AI_EGRESS if destination_host == ANTHROPIC_HOST else f"{AI_EGRESS}:{destination_host}"
    return require_consent(
        key,
        _AI_DETAILS.format(destination=destination_host),
        f"Send email content to {destination_host} to draft replies",
        accept_env=AI_EGRESS_ENV,
    )
