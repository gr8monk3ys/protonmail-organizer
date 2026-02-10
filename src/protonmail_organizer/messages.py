"""Message listing, search, display, and stats."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from .client_ext import ProtonMailExt
from .constants import INBOX, SYSTEM_LABELS, LABEL_TYPE_LABEL, LABEL_TYPE_FOLDER
from .display import (
    console,
    message_table,
    print_error,
    print_info,
    print_success,
    print_warning,
    stats_panel,
)


def list_messages(
    client: ProtonMailExt,
    folder: str = INBOX,
    limit: int = 20,
    page: int = 0,
) -> None:
    """List messages from a folder and display in a table."""
    folder_name = SYSTEM_LABELS.get(folder, folder)
    msgs = client.search_messages(label_id=folder, page=page, page_size=limit)

    if not msgs:
        print_warning(f"No messages in {folder_name}.")
        return

    table = message_table(msgs, title=f"{folder_name} (page {page + 1})")
    console.print(table)
    console.print(f"[dim]Showing {len(msgs)} messages. Use --page to paginate.[/dim]")


def search_messages(
    client: ProtonMailExt,
    keyword: Optional[str] = None,
    sender: Optional[str] = None,
    recipient: Optional[str] = None,
    begin: Optional[int] = None,
    has_attachments: Optional[bool] = None,
    label_id: Optional[str] = None,
    limit: int = 20,
) -> None:
    """Search messages and display results."""
    msgs = client.search_messages(
        keyword=keyword,
        sender=sender,
        recipient=recipient,
        begin=begin,
        has_attachments=has_attachments,
        label_id=label_id,
        page_size=limit,
    )

    if not msgs:
        print_warning("No messages found.")
        return

    # Build title from filters
    parts = []
    if keyword:
        parts.append(f'keyword="{keyword}"')
    if sender:
        parts.append(f"from={sender}")
    if recipient:
        parts.append(f"to={recipient}")
    title = "Search: " + ", ".join(parts) if parts else "Search Results"

    table = message_table(msgs, title=title)
    console.print(table)
    console.print(f"[dim]{len(msgs)} results[/dim]")


def read_message(client: ProtonMailExt, message_id: str) -> None:
    """Read and display a single message."""
    try:
        msg = client.read_message(message_id)
    except Exception as e:
        print_error(f"Failed to read message: {e}")
        return

    sender = getattr(msg, "sender", None)
    sender_str = f"{sender.name} <{sender.address}>" if sender else "?"
    date_str = datetime.fromtimestamp(msg.time).strftime("%Y-%m-%d %H:%M") if msg.time else ""

    console.print(Panel(
        f"[cyan]From:[/cyan] {sender_str}\n"
        f"[cyan]Subject:[/cyan] {msg.subject}\n"
        f"[cyan]Date:[/cyan] {date_str}\n"
        f"[cyan]ID:[/cyan] {msg.id}\n"
        f"\n{msg.body or '(empty body)'}",
        title="Message",
        border_style="blue",
    ))


def count_messages(client: ProtonMailExt, folder: Optional[str] = None) -> None:
    """Show message counts."""
    counts = client.get_messages_count()

    table = Table(title="Message Counts", show_lines=False)
    table.add_column("Folder", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Unread", justify="right", style="yellow")

    for entry in counts:
        label_id = entry.get("LabelID", "")
        if folder and label_id != folder:
            continue
        name = SYSTEM_LABELS.get(label_id, label_id)
        total = entry.get("Total", 0)
        unread = entry.get("Unread", 0)
        if total > 0 or label_id in SYSTEM_LABELS:
            unread_str = str(unread) if unread > 0 else ""
            table.add_row(name, str(total), unread_str)

    console.print(table)


def show_stats(client: ProtonMailExt) -> None:
    """Show account overview with counts and top senders."""
    # Message counts
    count_messages(client)

    # Top senders from inbox
    console.print()
    msgs = client.search_messages(label_id=INBOX, page_size=150)
    if msgs:
        sender_counts = Counter()
        for msg in msgs:
            sender = msg.get("Sender", {})
            addr = sender.get("Address", "unknown") if isinstance(sender, dict) else "unknown"
            sender_counts[addr] += 1

        table = Table(title="Top Senders (Inbox)", show_lines=False)
        table.add_column("Sender", style="cyan")
        table.add_column("Count", justify="right")

        for addr, cnt in sender_counts.most_common(10):
            table.add_row(addr, str(cnt))

        console.print(table)

    # Label counts
    console.print()
    user_labels = client.get_labels_by_type_id(1)  # actual labels (bug workaround)
    user_folders = client.get_labels_by_type_id(3)  # actual folders (bug workaround)
    info = {
        "Custom Labels": f"{len(user_labels)}/3 (free plan limit)",
        "Custom Folders": f"{len(user_folders)}/3 (free plan limit)",
    }
    console.print(stats_panel(info))


def digest_report(client: ProtonMailExt, days: int = 1) -> None:
    """Show a summary digest of email activity over the last N days.

    Includes:
    - New messages received (count by sender domain)
    - Unread count
    - Top senders (real people vs newsletters)
    """
    cutoff = int((datetime.now() - timedelta(days=days)).timestamp())

    print_info(f"Building digest for the last {days} day(s)...")

    # Fetch recent messages from inbox
    recent = client.search_messages_all(label_id=INBOX, begin=cutoff)
    if not recent:
        print_warning("No messages in the selected time period.")
        return

    # Counts
    total = len(recent)
    unread = sum(1 for m in recent if m.get("Unread", 0))

    # Count by sender domain
    domain_counts = Counter()
    sender_counts = Counter()
    real_people_unread = []

    # Newsletter detection heuristics (reuse from cleanup)
    newsletter_patterns = [
        r"noreply@", r"no-reply@", r"newsletter@", r"notifications?@",
        r"updates?@", r"marketing@", r"digest@", r"mailer@",
        r"mailchimp", r"sendgrid",
    ]

    for msg in recent:
        sender = msg.get("Sender", {})
        addr = sender.get("Address", "") if isinstance(sender, dict) else ""
        name = sender.get("Name", "") if isinstance(sender, dict) else ""

        domain = addr.split("@")[-1] if "@" in addr else "unknown"
        domain_counts[domain] += 1
        sender_counts[addr] += 1

        # Check if from a real person (not newsletter)
        is_newsletter = any(re.search(p, addr.lower()) for p in newsletter_patterns)
        if msg.get("Unread", 0) and not is_newsletter:
            real_people_unread.append({
                "from": name or addr,
                "subject": msg.get("Subject", "(no subject)"),
            })

    # Summary panel
    console.print(Panel(
        f"[cyan]Period:[/cyan] Last {days} day(s)\n"
        f"[cyan]Total messages:[/cyan] {total}\n"
        f"[cyan]Unread:[/cyan] {unread}\n"
        f"[cyan]Unique domains:[/cyan] {len(domain_counts)}",
        title="Digest Summary",
        border_style="blue",
    ))

    # Top sender domains
    table = Table(title="Messages by Sender Domain", show_lines=False)
    table.add_column("Domain", style="cyan")
    table.add_column("Count", justify="right")

    for domain, cnt in domain_counts.most_common(15):
        table.add_row(domain, str(cnt))

    console.print(table)

    # Action items: unread from real people
    if real_people_unread:
        console.print()
        action_table = Table(title="Action Items (Unread from People)", show_lines=False)
        action_table.add_column("From", style="cyan", max_width=30)
        action_table.add_column("Subject", style="white")

        for item in real_people_unread[:20]:
            action_table.add_row(item["from"], item["subject"])

        console.print(action_table)
    else:
        print_info("\nNo unread messages from real people. Inbox zero!")
