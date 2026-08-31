"""Bulk delete, archive, newsletter detection, and folder emptying."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .batch import batch_apply
from .client_ext import ProtonMailExt, sender_address, sender_parts
from .constants import (
    ARCHIVE,
    INBOX,
    SYSTEM_LABELS,
    TRASH,
)
from .display import (
    confirm_action,
    console,
    debug_enabled,
    message_table,
    print_info,
    print_success,
    print_warning,
    warn_if_truncated,
)
from .oplog import record_operation


def delete_old_messages(
    client: ProtonMailExt,
    days: int,
    folder: str = INBOX,
    dry_run: bool = False,
    permanent: bool = False,
    assume_yes: bool = False,
) -> None:
    """Delete messages older than N days. Moves to Trash unless permanent."""
    cutoff = int((datetime.now() - timedelta(days=days)).timestamp())
    folder_name = SYSTEM_LABELS.get(folder, folder)
    verb = "permanently delete" if permanent else "move to Trash"

    print_info(f"Finding messages older than {days} days in {folder_name}...")

    messages = client.search_messages_all(label_id=folder, end=cutoff)

    if not messages:
        print_warning("No messages found matching criteria.")
        return

    warn_if_truncated(messages)
    console.print(message_table(messages, title=f"Messages to {verb} ({len(messages)})"))

    if dry_run or not assume_yes:
        if not confirm_action(
            f"{verb} {len(messages)} messages from {folder_name}", len(messages), dry_run
        ):
            if not dry_run:
                print_warning("Cancelled.")
            return

    if permanent:
        ids = _batch_delete(client, messages)
        record_operation(
            f"Permanently deleted {len(ids)} message(s) from {folder_name}",
            ids,
            permanent=True,
        )
    else:
        ids = _batch_trash(client, messages)
        record_operation(
            f"Moved {len(ids)} message(s) from {folder_name} to Trash",
            ids,
            added_label=TRASH,
            removed_label=folder,
        )


def archive_by_sender(
    client: ProtonMailExt,
    pattern: str,
    dry_run: bool = False,
) -> None:
    """Archive messages matching a sender pattern."""
    print_info(f"Finding messages from sender matching '{pattern}'...")

    messages = client.search_messages_all(sender=pattern, label_id=INBOX)

    if not messages:
        print_warning(f"No messages from '{pattern}' found in Inbox.")
        return

    warn_if_truncated(messages)
    console.print(message_table(messages, title=f"Messages to archive ({len(messages)})"))

    if not confirm_action(
        f"archive {len(messages)} messages from '{pattern}'", len(messages), dry_run
    ):
        if not dry_run:
            print_warning("Cancelled.")
        return

    ids = _batch_label(client, ARCHIVE, messages, action="archive")
    record_operation(
        f"Archived {len(ids)} message(s) from '{pattern}'",
        ids,
        added_label=ARCHIVE,
        removed_label=INBOX,
    )


def handle_newsletters(
    client: ProtonMailExt,
    dry_run: bool = False,
    do_delete: bool = False,
    permanent: bool = False,
    assume_yes: bool = False,
) -> None:
    """Detect newsletters and optionally remove them (to Trash unless permanent)."""
    print_info("Scanning inbox for newsletters...")

    messages = client.search_messages_all(label_id=INBOX)
    warn_if_truncated(messages)
    newsletters = [m for m in messages if _is_newsletter(m)]

    if not newsletters:
        print_warning("No newsletters detected.")
        return

    console.print(message_table(newsletters, title=f"Detected Newsletters ({len(newsletters)})"))

    if not do_delete:
        print_info("Use --delete to remove these messages.")
        return

    verb = "permanently delete" if permanent else "move to Trash"
    if dry_run or not assume_yes:
        if not confirm_action(f"{verb} detected newsletters", len(newsletters), dry_run):
            if not dry_run:
                print_warning("Cancelled.")
            return

    if permanent:
        ids = _batch_delete(client, newsletters)
        record_operation(f"Permanently deleted {len(ids)} newsletter(s)", ids, permanent=True)
    else:
        ids = _batch_trash(client, newsletters)
        record_operation(
            f"Moved {len(ids)} newsletter(s) to Trash",
            ids,
            added_label=TRASH,
            removed_label=INBOX,
        )


def empty_folder(
    client: ProtonMailExt,
    label_id: str,
    skip_confirm: bool = False,
) -> None:
    """Empty all messages from a folder (Trash, Spam, etc.)."""
    folder_name = SYSTEM_LABELS.get(label_id, label_id)
    print_info(f"Fetching all messages from {folder_name}...")

    messages = client.search_messages_all(label_id=label_id)

    if not messages:
        print_warning(f"{folder_name} is already empty.")
        return

    warn_if_truncated(messages)

    if not skip_confirm:
        if not confirm_action(f"permanently delete all from {folder_name}", len(messages)):
            print_warning("Cancelled.")
            return

    ids = _batch_delete(client, messages)
    record_operation(f"Emptied {folder_name} ({len(ids)} message(s))", ids, permanent=True)


# --- Helpers ---


def _ids_of(messages: list) -> list:
    """Extract message IDs from dicts or Message objects."""
    return [m.get("ID", m.id if hasattr(m, "id") else m) for m in messages]


def _batch_delete(client: ProtonMailExt, messages: list) -> list:
    """Permanently delete messages in batches. Returns the affected IDs."""
    ids = _ids_of(messages)
    failed = batch_apply(client.delete_messages, ids, "Deleting")
    print_success(f"Deleted {len(ids) - failed} messages.")
    return ids


def _batch_trash(client: ProtonMailExt, messages: list) -> list:
    """Move messages to Trash (recoverable) in batches. Returns the affected IDs."""
    ids = _ids_of(messages)
    failed = batch_apply(
        lambda chunk: client.set_label_for_messages(TRASH, chunk), ids, "Moving to Trash"
    )
    print_success(f"Moved {len(ids) - failed} messages to Trash. Run 'pmo undo' to restore.")
    return ids


def _batch_label(
    client: ProtonMailExt,
    label_id: str,
    messages: list,
    action: str = "label",
) -> list:
    """Apply a label to messages in batches. Returns the affected IDs."""
    ids = _ids_of(messages)
    failed = batch_apply(
        lambda chunk: client.set_label_for_messages(label_id, chunk),
        ids,
        action.capitalize() + "ing",
    )
    print_success(f"{action.capitalize()}d {len(ids) - failed} messages.")
    return ids


# Newsletter detection heuristics
_NEWSLETTER_HEADERS = [
    "list-unsubscribe",
    "x-mailer",
    "x-campaign",
    "x-mailgun",
    "x-sendgrid",
]

_NEWSLETTER_SENDER_PATTERNS = [
    r"noreply@",
    r"no-reply@",
    r"newsletter@",
    r"news@",
    r"digest@",
    r"notifications?@",
    r"updates?@",
    r"marketing@",
    r"info@",
    r"hello@",
    r"mailer@",
    r"campaign",
    r"mailchimp",
    r"sendgrid",
    r"constantcontact",
]

_NEWSLETTER_SUBJECT_PATTERNS = [
    r"newsletter",
    r"digest",
    r"weekly.*update",
    r"monthly.*update",
    r"unsubscribe",
    r"your.*summary",
]


def find_unsubscribe_links(client: ProtonMailExt, limit: int = 50) -> None:
    """Find messages with List-Unsubscribe headers and show unsubscribe links."""
    print_info("Scanning inbox for messages with unsubscribe links...")

    messages = client.search_messages(label_id=INBOX, page_size=limit)
    if not messages:
        print_warning("No messages in inbox.")
        return

    unsubscribe_entries = []

    for msg_summary in messages:
        msg_id = msg_summary.get("ID", "")
        if not msg_id:
            continue

        # Get full message to check headers
        try:
            full_msg = client.get_message(msg_id)
        except Exception as e:
            # One bad message shouldn't abort the scan, but surface it on demand.
            if debug_enabled():
                console.print(f"[dim]skipped message {msg_id}: {e}[/dim]")
            continue

        # Check parsed headers for List-Unsubscribe
        headers = full_msg.get("ParsedHeaders", {})
        unsub = headers.get("List-Unsubscribe", "")

        if not unsub:
            # Also check the raw Header field
            raw_header = full_msg.get("Header", "")
            match = re.search(r"List-Unsubscribe:\s*(.+)", raw_header, re.IGNORECASE)
            if match:
                unsub = match.group(1).strip()

        if unsub:
            name, addr = sender_parts(msg_summary)

            # Extract URLs from the header value
            urls = re.findall(r"<(https?://[^>]+)>", unsub)
            mailto = re.findall(r"<(mailto:[^>]+)>", unsub)

            unsubscribe_entries.append(
                {
                    "sender": name or addr,
                    "address": addr,
                    "urls": urls,
                    "mailto": mailto,
                }
            )

    if not unsubscribe_entries:
        print_warning("No messages with unsubscribe links found.")
        return

    # Deduplicate by sender address
    seen_addrs = set()
    unique_entries = []
    for entry in unsubscribe_entries:
        if entry["address"] not in seen_addrs:
            seen_addrs.add(entry["address"])
            unique_entries.append(entry)

    from rich.table import Table

    table = Table(title=f"Unsubscribe Links ({len(unique_entries)} senders)", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Sender", style="cyan", max_width=30)
    table.add_column("Unsubscribe URL", style="blue")

    for i, entry in enumerate(unique_entries, 1):
        url = (
            entry["urls"][0]
            if entry["urls"]
            else (entry["mailto"][0] if entry["mailto"] else "(header only)")
        )
        table.add_row(str(i), entry["sender"], url)

    console.print(table)
    print_info(f"\nFound {len(unique_entries)} unique senders with unsubscribe links.")
    print_info("Visit the URLs above to unsubscribe from each sender.")


def _is_newsletter(msg: dict) -> bool:
    """Heuristic: check if a message looks like a newsletter."""
    addr = sender_address(msg)
    subject = msg.get("Subject", "")

    addr_lower = addr.lower()
    subj_lower = subject.lower()

    for pattern in _NEWSLETTER_SENDER_PATTERNS:
        if re.search(pattern, addr_lower):
            return True

    for pattern in _NEWSLETTER_SUBJECT_PATTERNS:
        if re.search(pattern, subj_lower):
            return True

    return False
