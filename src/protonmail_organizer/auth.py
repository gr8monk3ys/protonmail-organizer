"""Authentication and session management."""

from __future__ import annotations

import os
import sys
from typing import Optional

import click
from rich.console import Console

from .client_ext import ProtonMailExt
from .config import SESSION_FILE, ensure_config_dir

console = Console()


def get_authenticated_client(require_auth: bool = True) -> Optional[ProtonMailExt]:
    """Return an authenticated ProtonMailExt client.

    Tries to load a saved session first. If no session exists and
    require_auth is True, prompts for interactive login.
    """
    client = ProtonMailExt()

    # Try loading saved session
    if SESSION_FILE.exists():
        try:
            client.load_session(str(SESSION_FILE), auto_save=True)
            return client
        except Exception as e:
            console.print(f"[yellow]Session expired or invalid: {e}[/yellow]")

    if not require_auth:
        return None

    # Interactive login
    return interactive_login(client)


def interactive_login(client: Optional[ProtonMailExt] = None) -> ProtonMailExt:
    """Prompt for credentials and log in."""
    if client is None:
        client = ProtonMailExt()

    console.print("[bold]ProtonMail Login[/bold]")
    username = click.prompt("Email")
    password = click.prompt("Password", hide_input=True)

    def get_2fa() -> str:
        return click.prompt("2FA code")

    try:
        client.login(username, password, getter_2fa_code=get_2fa)
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        sys.exit(1)

    # Save session with restrictive permissions
    ensure_config_dir()
    client.save_session(str(SESSION_FILE))
    os.chmod(SESSION_FILE, 0o600)  # owner read/write only
    console.print("[green]Logged in and session saved.[/green]")
    return client


def logout() -> None:
    """Remove saved session file."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
        console.print("[green]Session removed.[/green]")
    else:
        console.print("[yellow]No active session.[/yellow]")


def session_status() -> None:
    """Show whether a valid session exists."""
    if not SESSION_FILE.exists():
        console.print("[yellow]No saved session.[/yellow]")
        return

    client = ProtonMailExt()
    try:
        client.load_session(str(SESSION_FILE), auto_save=False)
        info = client.get_user_info()
        user = info.get("User", {})
        email = user.get("Email", "unknown")
        display = user.get("DisplayName", "")
        console.print(f"[green]Authenticated as:[/green] {display} <{email}>")
    except Exception as e:
        console.print(f"[red]Session invalid: {e}[/red]")
