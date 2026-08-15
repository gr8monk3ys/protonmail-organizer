"""Polling watch mode for continuous inbox organization."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from rich.table import Table

from .client_ext import ProtonMailExt
from .constants import INBOX
from .display import console, print_error, print_info, print_success
from .rules import _apply_actions, _load_rules, _matches_conditions


def watch_inbox(
    client: ProtonMailExt,
    interval: int = 60,
    rules_file: Optional[str] = None,
) -> None:
    """Poll for new messages and auto-apply rules continuously.

    Args:
        client: Authenticated ProtonMail client.
        interval: Seconds between polls.
        rules_file: Path to rules YAML (default: config rules file).
    """
    rules = _load_rules(rules_file)
    if not rules:
        print_error("No rules loaded. Cannot watch.")
        return

    # Build label map
    all_labels = client.get_all_labels()
    label_map = {}
    for label in all_labels:
        label_map[label.name.lower()] = label.id
    from .constants import SYSTEM_LABELS

    for label_id, name in SYSTEM_LABELS.items():
        label_map[name.lower()] = label_id

    # Track seen message IDs to only process new ones
    seen_ids: set[str] = set()
    action_log: list[dict] = []

    # Seed with current inbox messages so we don't re-process them
    print_info("Seeding with current inbox state...")
    current = client.search_messages_all(label_id=INBOX)
    for msg in current:
        seen_ids.add(msg.get("ID", ""))

    print_success(f"Watching inbox — checking every {interval}s. Ctrl+C to stop.")
    print_info(f"Loaded {len(rules)} rule(s). Tracking {len(seen_ids)} existing message(s).\n")

    try:
        while True:
            _poll_cycle(client, rules, label_map, seen_ids, action_log)
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print()
        print_info("Watch stopped.")
        if action_log:
            _show_summary(action_log)


def _poll_cycle(
    client: ProtonMailExt,
    rules: list,
    label_map: dict,
    seen_ids: set,
    action_log: list,
) -> None:
    """Single poll cycle: fetch inbox, find new messages, apply rules."""
    now = datetime.now().strftime("%H:%M:%S")

    try:
        # Only fetch the most recent page — seen_ids filters out old messages
        messages = client.search_messages(label_id=INBOX, page_size=50)
    except Exception as e:
        console.print(f"[dim]{now}[/dim] [red]Poll failed: {e}[/red]")
        return

    new_messages = [m for m in messages if m.get("ID", "") not in seen_ids]

    if not new_messages:
        console.print(f"[dim]{now} — no new messages[/dim]")
        return

    console.print(f"[dim]{now}[/dim] [cyan]{len(new_messages)} new message(s)[/cyan]")

    for msg in new_messages:
        seen_ids.add(msg.get("ID", ""))

    # Apply each rule once per cycle to all its matches, rather than once per
    # message — fewer API calls, and one oplog entry per rule instead of a
    # flood of single-message entries evicting the undo history.
    unmatched_ids = {m.get("ID", "") for m in new_messages}
    for rule in rules:
        name = rule.get("name", "Unnamed")
        conditions = rule.get("conditions", {})
        actions = rule.get("actions", {})

        matched = [m for m in new_messages if _matches_conditions(m, conditions)]
        if not matched:
            continue

        for msg in matched:
            unmatched_ids.discard(msg.get("ID", ""))
            addr, subject = _sender_and_subject(msg)
            console.print(f"  [green]>[/green] [bold]{name}[/bold] → {addr} | {subject}")

        try:
            _apply_actions(client, matched, actions, label_map)
            for msg in matched:
                addr, subject = _sender_and_subject(msg)
                action_log.append(
                    {"time": now, "rule": name, "sender": addr, "subject": subject}
                )
        except Exception as e:
            console.print(f"  [red]Failed to apply rule '{name}': {e}[/red]")

    for msg in new_messages:
        if msg.get("ID", "") in unmatched_ids:
            addr, subject = _sender_and_subject(msg)
            console.print(f"  [dim]  No rules matched: {addr} | {subject}[/dim]")


def _sender_and_subject(msg: dict) -> tuple[str, str]:
    """Sender address and truncated subject for log lines."""
    sender = msg.get("Sender", {})
    addr = sender.get("Address", "") if isinstance(sender, dict) else ""
    return addr, msg.get("Subject", "")[:50]


def _show_summary(action_log: list) -> None:
    """Show summary of actions taken during watch session."""
    console.print()
    table = Table(title="Watch Session Summary", show_lines=False)
    table.add_column("Time", style="dim", width=10)
    table.add_column("Rule", style="cyan")
    table.add_column("Sender", style="white", max_width=30)
    table.add_column("Subject", style="dim")

    for entry in action_log[-20:]:  # last 20 actions
        table.add_row(
            entry["time"],
            entry["rule"],
            entry["sender"],
            entry["subject"],
        )

    console.print(table)
    print_info(f"Total actions: {len(action_log)}")
