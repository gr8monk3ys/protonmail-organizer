"""Rich terminal output helpers for tables, confirmations, and progress."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def debug_enabled() -> bool:
    """True when PMO_DEBUG=1.

    Enables verbose tracebacks, which are the quickest way to spot when the
    unofficial upstream API has changed shape underneath us.
    """
    return os.environ.get("PMO_DEBUG") == "1"


def message_table(messages: list, title: str = "Messages") -> Table:
    """Build a Rich table for a list of messages (dicts or Message objects)."""
    table = Table(title=title, show_lines=False, expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("From", style="cyan", max_width=30)
    table.add_column("Subject", style="white")
    table.add_column("Date", style="green", width=12)
    table.add_column("", width=3)  # flags

    for i, msg in enumerate(messages, 1):
        sender = _get_sender(msg)
        subject = _get_field(msg, "Subject", "subject", "(no subject)")
        time_val = _get_field(msg, "Time", "time", 0)
        date_str = _format_time(time_val)
        unread = _get_field(msg, "Unread", "unread", False)
        has_att = bool(_get_field(msg, "NumAttachments", "attachments", None))

        flags = ""
        if unread:
            flags += "[bold yellow]*[/bold yellow]"
        if has_att:
            flags += "[dim]@[/dim]"

        style = "bold" if unread else ""
        table.add_row(str(i), sender, subject, date_str, flags, style=style)

    return table


def label_table(labels: list, title: str = "Labels") -> Table:
    """Build a Rich table for a list of labels."""
    table = Table(title=title, show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="yellow", width=8)
    table.add_column("Color", width=8)
    table.add_column("ID", style="dim", max_width=20)

    for label in labels:
        name = _get_field(label, "Name", "name", "?")
        color = _get_field(label, "Color", "color", "")
        label_id = _get_field(label, "ID", "id", "")
        type_name = _get_field(label, "type_name", "type_name", "")
        if not type_name:
            type_id = _get_field(label, "Type", "type", 0)
            type_name = {1: "label", 3: "folder", 4: "system"}.get(type_id, str(type_id))

        color_display = f"[{color}]{color}[/{color}]" if color else ""
        table.add_row(name, type_name, color_display, str(label_id))

    return table


def stats_panel(stats: dict) -> Panel:
    """Build a Rich panel showing account stats."""
    lines = []
    for key, value in stats.items():
        lines.append(f"[cyan]{key}:[/cyan] {value}")
    return Panel("\n".join(lines), title="Account Stats", border_style="blue")


def confirm_action(message: str, count: int, dry_run: bool = False) -> bool:
    """Ask for confirmation before destructive action. Auto-yes in dry_run mode."""
    if dry_run:
        console.print(f"[yellow][DRY RUN][/yellow] Would {message} ({count} items)")
        return False
    console.print(f"\n[bold red]About to {message} ({count} items)[/bold red]")
    return console.input("[yellow]Proceed? (y/N): [/yellow]").strip().lower() == "y"


def progress_context(description: str = "Processing..."):
    """Return a Rich progress context manager."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    )


def print_success(msg: str) -> None:
    console.print(f"[green]{msg}[/green]")


def print_warning(msg: str) -> None:
    console.print(f"[yellow]{msg}[/yellow]")


def print_error(msg: str) -> None:
    console.print(f"[red]{msg}[/red]")
    # If we're handling an exception and the user opted into PMO_DEBUG, show the
    # full traceback so an opaque "Failed to ...: <msg>" can be diagnosed.
    if debug_enabled() and sys.exc_info()[0] is not None:
        console.print_exception()


def print_info(msg: str) -> None:
    console.print(f"[blue]{msg}[/blue]")


# --- Helpers ---


def _get_sender(msg: Any) -> str:
    """Extract sender display string from message dict or object."""
    if isinstance(msg, dict):
        sender = msg.get("Sender") or msg.get("sender", {})
        if isinstance(sender, dict):
            name = sender.get("Name", "")
            addr = sender.get("Address", "")
            return name if name else addr
        return str(sender)
    # Message object
    sender = getattr(msg, "sender", None)
    if sender is None:
        return "?"
    name = getattr(sender, "name", "")
    addr = getattr(sender, "address", "")
    return name if name else addr


def _get_field(obj: Any, dict_key: str, attr_key: str, default: Any = None) -> Any:
    """Get a field from a dict or object."""
    if isinstance(obj, dict):
        return obj.get(dict_key, default)
    return getattr(obj, attr_key, default)


def _format_time(timestamp: Any) -> str:
    """Format a unix timestamp to a short date string."""
    if not timestamp:
        return ""
    try:
        dt = datetime.fromtimestamp(int(timestamp))
        now = datetime.now()
        if dt.date() == now.date():
            return dt.strftime("%H:%M")
        if dt.year == now.year:
            return dt.strftime("%b %d")
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return ""
