"""Label and folder CRUD with free-plan guards."""

from __future__ import annotations

from typing import Optional

from .client_ext import ProtonMailExt
from .constants import (
    DEFAULT_LABEL_COLOR,
    FREE_PLAN_MAX_FOLDERS,
    FREE_PLAN_MAX_LABELS,
    LABEL_TYPE_FOLDER,
    LABEL_TYPE_LABEL,
)
from .display import (
    console,
    label_table,
    print_error,
    print_success,
    print_warning,
)


def list_labels(client: ProtonMailExt, label_type: str = "all") -> None:
    """List labels/folders, filtered by type."""
    if label_type == "labels":
        # NOTE: get_labels_by_type_id(1) returns actual labels (library bug workaround)
        labels = client.get_labels_by_type_id(1)
        title = "User Labels"
    elif label_type == "folders":
        # NOTE: get_labels_by_type_id(3) returns actual folders (library bug workaround)
        labels = client.get_labels_by_type_id(3)
        title = "User Folders"
    elif label_type == "system":
        labels = client.get_system_labels()
        title = "System Labels"
    else:
        labels = client.get_all_labels()
        title = "All Labels"

    if not labels:
        print_warning(f"No {label_type} found.")
        return

    table = label_table(labels, title=title)
    console.print(table)


def create_label(
    client: ProtonMailExt,
    name: str,
    color: str = DEFAULT_LABEL_COLOR,
    label_type: int = LABEL_TYPE_LABEL,
) -> Optional[dict]:
    """Create a label or folder, checking free-plan limits first."""
    # Check limits
    type_name = "folder" if label_type == LABEL_TYPE_FOLDER else "label"
    existing = client.get_labels_by_type_id(label_type)
    max_allowed = FREE_PLAN_MAX_FOLDERS if label_type == LABEL_TYPE_FOLDER else FREE_PLAN_MAX_LABELS

    if len(existing) >= max_allowed:
        print_error(
            f"Free plan limit reached: {len(existing)}/{max_allowed} {type_name}s. "
            f"Delete one first or upgrade."
        )
        return None

    try:
        result = client.create_label(name, color, label_type)
        print_success(
            f"Created {type_name} '{name}' "
            f"({len(existing) + 1}/{max_allowed} used)"
        )
        return result
    except Exception as e:
        print_error(f"Failed to create {type_name}: {e}")
        return None


def delete_label(
    client: ProtonMailExt,
    label_id: str,
    skip_confirm: bool = False,
) -> None:
    """Delete a label or folder by ID."""
    if not skip_confirm:
        confirm = console.input(
            f"[yellow]Delete label/folder {label_id}? (y/N): [/yellow]"
        ).strip().lower()
        if confirm != "y":
            print_warning("Cancelled.")
            return

    try:
        client.delete_label(label_id)
        print_success(f"Deleted label/folder {label_id}")
    except Exception as e:
        print_error(f"Failed to delete: {e}")


def apply_label(
    client: ProtonMailExt,
    label_id: str,
    message_ids: list,
    remove: bool = False,
) -> None:
    """Apply or remove a label from messages."""
    action = "remove" if remove else "apply"
    try:
        if remove:
            client.unset_label_for_messages(label_id, message_ids)
        else:
            client.set_label_for_messages(label_id, message_ids)
        print_success(f"Label {action} to {len(message_ids)} message(s)")
    except Exception as e:
        print_error(f"Failed to {action} label: {e}")
