"""Operation log for reversible bulk actions.

Records bulk cleanup operations (delete-to-trash, archive) so they can be
reversed with ``pmo undo``. Each entry is modeled as a label change: a label
that was *added* and/or a label that was *removed*. Undo re-adds the removed
label and removes the added one.

Permanent deletes (emptying Trash, ``--permanent``) are recorded too, but for
audit only — they cannot be undone.

Stored at ~/.config/protonmail-organizer/operations.json (mode 0600).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import click
from rich.table import Table

from .batch import batch_apply
from .client_ext import ProtonMailExt
from .config import CONFIG_DIR, ensure_config_dir, write_private
from .constants import SYSTEM_LABELS
from .display import console, print_error, print_info, print_success, print_warning

OPLOG_FILE = CONFIG_DIR / "operations.json"
MAX_OPS = 50


def _load() -> list:
    """Load the operation log (most recent last)."""
    if not OPLOG_FILE.exists():
        return []
    try:
        data = json.loads(OPLOG_FILE.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(ops: list) -> None:
    """Persist the operation log with restrictive permissions."""
    ensure_config_dir()
    write_private(OPLOG_FILE, json.dumps(ops[-MAX_OPS:], indent=2))


def record_operation(
    description: str,
    message_ids: list,
    added_label: Optional[str] = None,
    removed_label: Optional[str] = None,
    permanent: bool = False,
) -> None:
    """Append a bulk operation to the log so it can be reviewed/undone.

    Args:
        description: Human-readable summary (e.g. "Deleted 12 messages").
        message_ids: IDs the operation affected.
        added_label: Label ID the operation applied (undo removes it).
        removed_label: Label ID the operation removed (undo restores it).
        permanent: True for irreversible operations (audit only).
    """
    if not message_ids:
        return
    ops = _load()
    ops.append(
        {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "description": description,
            "message_ids": list(message_ids),
            "added_label": added_label,
            "removed_label": removed_label,
            "permanent": permanent,
        }
    )
    _save(ops)


def list_operations() -> None:
    """Show recent logged operations."""
    ops = _load()
    if not ops:
        print_info("No operations logged yet.")
        return

    table = Table(title="Recent Operations (newest last)", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("When", style="green", width=20)
    table.add_column("Operation", style="cyan")
    table.add_column("Msgs", justify="right", width=6)
    table.add_column("Undoable", width=9)

    for i, op in enumerate(ops, 1):
        undoable = "[red]no[/red]" if op.get("permanent") else "[green]yes[/green]"
        table.add_row(
            str(i),
            op.get("ts", ""),
            op.get("description", ""),
            str(len(op.get("message_ids", []))),
            undoable,
        )

    console.print(table)
    print_info("Run 'pmo undo' to reverse the most recent undoable operation.")


def undo_last(client: ProtonMailExt, assume_yes: bool = False) -> None:
    """Reverse the most recent logged operation (confirming first unless assume_yes)."""
    ops = _load()
    if not ops:
        print_warning("Nothing to undo.")
        return

    op = ops[-1]
    desc = op.get("description", "operation")

    if op.get("permanent"):
        print_error(f"The last operation ({desc}) was permanent and cannot be undone.")
        print_info("Run 'pmo undo --list' to see the operation history.")
        return

    ids = op.get("message_ids", [])
    added = op.get("added_label")
    removed = op.get("removed_label")

    if not assume_yes and not click.confirm(
        f"Undo '{desc}' ({len(ids)} message(s))?", default=False
    ):
        print_warning("Cancelled.")
        return

    print_info(f"Undoing: {desc} ({len(ids)} message(s))...")
    # Restore the removed label first (re-files into the source folder),
    # then strip the label the operation added.
    failed = 0
    if removed:
        failed = batch_apply(
            lambda b: client.set_label_for_messages(removed, b), ids, "Restoring", progress=False
        )
    if not failed and added:
        failed = batch_apply(
            lambda b: client.unset_label_for_messages(added, b), ids, "Unlabeling", progress=False
        )
    if failed:
        print_error(
            f"Undo incomplete ({failed} message(s) failed) — keeping the operation in the log."
        )
        return

    ops.pop()
    _save(ops)
    print_success(f"Undid: {desc}")


def label_name(label_id: Optional[str]) -> str:
    """Friendly name for a label ID (for descriptions)."""
    if not label_id:
        return ""
    return SYSTEM_LABELS.get(label_id, label_id)
