"""YAML-based rule engine for auto-organizing messages."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

from .batch import batch_apply
from .client_ext import ProtonMailExt, sender_address
from .config import RULES_FILE, ensure_config_dir
from .constants import (
    ARCHIVE,
    DESTRUCTIVE_ACTIONS,
    FREE_PLAN_MAX_FOLDERS,
    FREE_PLAN_MAX_LABELS,
    INBOX,
    LABEL_TYPE_FOLDER,
    LABEL_TYPE_LABEL,
    STARRED,
    SYSTEM_LABELS,
    TRASH,
)
from .display import (
    confirm_action,
    console,
    message_table,
    print_error,
    print_info,
    print_success,
    print_warning,
    warn_if_truncated,
)
from .oplog import record_operation

EXAMPLE_RULES = """\
# ProtonMail Organizer Rules
# Each rule has conditions (all must match) and actions to apply.

rules:
  - name: "Archive old promotions"
    conditions:
      sender_contains: "promo"
      older_than_days: 30
    actions:
      archive: true

  - name: "Label GitHub notifications"
    conditions:
      sender_domain: "github.com"
    actions:
      add_label: "GitHub"
      mark_read: true

  - name: "Star important contacts"
    conditions:
      sender_is: "boss@company.com"
    actions:
      star: true

  # "delete" moves messages to Trash (recoverable with 'pmo undo').
  - name: "Delete old newsletters"
    conditions:
      sender_contains: "newsletter"
      older_than_days: 60
      unread: true
    actions:
      delete: true
"""


def _get_rules_path(rules_file: Optional[str] = None) -> Path:
    """Resolve the rules file path."""
    if rules_file:
        return Path(rules_file)
    return RULES_FILE


def load_rules(rules_file: Optional[str] = None) -> list:
    """Load and parse rules from YAML file."""
    path = _get_rules_path(rules_file)
    if not path.exists():
        print_error(f"Rules file not found: {path}")
        print_info("Run 'pmo rules init' to create an example rules file.")
        return []

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "rules" not in data:
        print_error("Invalid rules file: missing 'rules' key.")
        return []

    return data["rules"]


def init_rules() -> None:
    """Create an example rules file."""
    ensure_config_dir()
    path = RULES_FILE

    if path.exists():
        print_warning(f"Rules file already exists: {path}")
        confirm = console.input("[yellow]Overwrite? (y/N): [/yellow]").strip().lower()
        if confirm != "y":
            return

    path.write_text(EXAMPLE_RULES)
    print_success(f"Created example rules at: {path}")


def list_rules(rules_file: Optional[str] = None) -> None:
    """Display all configured rules."""
    rules = load_rules(rules_file)
    if not rules:
        return

    for i, rule in enumerate(rules, 1):
        name = rule.get("name", f"Rule {i}")
        conditions = rule.get("conditions", {})
        actions = rule.get("actions", {})

        console.print(f"\n[bold cyan]Rule {i}: {name}[/bold cyan]")
        console.print("  [yellow]Conditions:[/yellow]")
        for key, val in conditions.items():
            console.print(f"    {key}: {val}")
        console.print("  [green]Actions:[/green]")
        for key, val in actions.items():
            console.print(f"    {key}: {val}")

    console.print(f"\n[dim]{len(rules)} rule(s) configured[/dim]")


def validate_rules(
    client: ProtonMailExt,
    rules_file: Optional[str] = None,
) -> bool:
    """Validate rules syntax and label references."""
    rules = load_rules(rules_file)
    if not rules:
        return False

    # Get existing labels for validation
    user_labels = client.get_labels_by_type_id(LABEL_TYPE_LABEL)
    user_folders = client.get_labels_by_type_id(LABEL_TYPE_FOLDER)
    label_names = {lbl.name.lower() for lbl in user_labels}
    folder_names = {f.name.lower() for f in user_folders}
    all_names = label_names | folder_names | {v.lower() for v in SYSTEM_LABELS.values()}

    valid = True
    referenced_new_labels = set()
    referenced_new_folders = set()

    for i, rule in enumerate(rules, 1):
        name = rule.get("name", f"Rule {i}")
        conditions = rule.get("conditions", {})
        actions = rule.get("actions", {})

        if not conditions:
            print_error(f"Rule '{name}': no conditions specified")
            valid = False

        if not actions:
            print_error(f"Rule '{name}': no actions specified")
            valid = False

        # Validate condition keys
        valid_conditions = {
            "sender_is",
            "sender_contains",
            "sender_domain",
            "subject_contains",
            "sender_matches",
            "subject_matches",
            "has_attachment",
            "older_than_days",
            "unread",
        }
        for key in conditions:
            if key not in valid_conditions:
                print_error(f"Rule '{name}': unknown condition '{key}'")
                valid = False

        # Validate action keys and label references
        valid_actions = {
            "move_to",
            "add_label",
            "remove_label",
            "mark_read",
            "delete",
            "archive",
            "star",
        }
        for key in actions:
            if key not in valid_actions:
                print_error(f"Rule '{name}': unknown action '{key}'")
                valid = False

        # Check label/folder references. move_to creates folders, which have
        # their own free-plan quota, separate from labels.
        for action_key in ("add_label", "remove_label"):
            target = actions.get(action_key)
            if target and target.lower() not in all_names:
                referenced_new_labels.add(target)
        move_target = actions.get("move_to")
        if move_target and move_target.lower() not in all_names:
            referenced_new_folders.add(move_target)

    # Check free-plan limits per kind
    _warn_quota(referenced_new_labels, "label", FREE_PLAN_MAX_LABELS - len(user_labels))
    _warn_quota(referenced_new_folders, "folder", FREE_PLAN_MAX_FOLDERS - len(user_folders))

    if valid:
        print_success(f"All {len(rules)} rule(s) are valid.")
    return valid


def _warn_quota(names: set, kind: str, available: int) -> None:
    """Report referenced-but-missing labels/folders against the free-plan quota."""
    if not names:
        return
    if len(names) > available:
        print_warning(
            f"Rules reference {len(names)} {kind}(s) that don't exist yet: {names}. "
            f"Only {available} more can be created on the free plan."
        )
    else:
        print_info(
            f"Rules reference {len(names)} new {kind}(s): {names}. "
            f"They will be created when rules run."
        )


def run_rules(
    client: ProtonMailExt,
    rules_file: Optional[str] = None,
    dry_run: bool = False,
    folder: str = INBOX,
) -> None:
    """Run rules against the messages in a folder (default: Inbox)."""
    rules = load_rules(rules_file)
    if not rules:
        return

    folder_name = SYSTEM_LABELS.get(folder, folder)
    print_info(f"Fetching {folder_name} messages...")
    messages = client.search_messages_all(label_id=folder)

    if not messages:
        print_warning(f"No messages in {folder_name}.")
        return

    warn_if_truncated(messages)
    print_info(f"Evaluating {len(rules)} rule(s) against {len(messages)} message(s)...")

    # Build label name -> ID mapping
    all_labels = client.get_all_labels()
    label_map = {}
    for label in all_labels:
        label_map[label.name.lower()] = label.id

    # Also add system labels by name
    for label_id, name in SYSTEM_LABELS.items():
        label_map[name.lower()] = label_id

    # Evaluate each rule
    total_matched = 0
    for rule in rules:
        name = rule.get("name", "Unnamed rule")
        conditions = rule.get("conditions", {})
        actions = rule.get("actions", {})

        matched = [m for m in messages if matches_conditions(m, conditions)]
        if not matched:
            continue

        console.print(f"\n[cyan]Rule '{name}':[/cyan] matched {len(matched)} message(s)")

        if dry_run:
            total_matched += len(matched)
            console.print(
                message_table(
                    matched[:10],
                    title=f"[DRY RUN] Would apply: {actions}",
                )
            )
            if len(matched) > 10:
                console.print(f"[dim]  ...and {len(matched) - 10} more[/dim]")
            continue

        destructive = any(actions.get(a) for a in DESTRUCTIVE_ACTIONS)
        if destructive and not confirm_action(
            f"move {len(matched)} message(s) matched by rule '{name}' to Trash",
            len(matched),
        ):
            print_warning(f"Skipped rule '{name}'.")
            continue

        total_matched += len(matched)
        apply_actions(client, matched, actions, label_map, source_folder=folder)

    if total_matched == 0:
        print_info("No messages matched any rules.")
    elif dry_run:
        print_info(f"\n[DRY RUN] {total_matched} message(s) matched across all rules.")
    else:
        print_success(f"Applied rules to {total_matched} message(s).")


def _as_list(value) -> list:
    """Normalize a scalar or list condition value into a list (for OR matching)."""
    return value if isinstance(value, list) else [value]


def _any(value, predicate) -> bool:
    """True if predicate matches any item of a scalar/list condition value (OR)."""
    return any(predicate(v) for v in _as_list(value))


def matches_conditions(msg: dict, conditions: dict) -> bool:
    """Check if a message matches all conditions (AND across keys).

    A condition value may be a scalar or a list; a list matches if ANY of its
    values match (OR within a single condition).
    """
    addr = sender_address(msg)
    subject = msg.get("Subject", "")
    domain = addr.split("@")[-1] if "@" in addr else ""
    msg_time = msg.get("Time", 0)
    unread = msg.get("Unread", 0)
    num_att = msg.get("NumAttachments", 0)

    for key, value in conditions.items():
        if key == "sender_is":
            if not _any(value, lambda v: addr.lower() == str(v).lower()):
                return False

        elif key == "sender_contains":
            if not _any(value, lambda v: str(v).lower() in addr.lower()):
                return False

        elif key == "sender_domain":
            if not _any(value, lambda v: domain.lower() == str(v).lower()):
                return False

        elif key == "subject_contains":
            if not _any(value, lambda v: str(v).lower() in subject.lower()):
                return False

        elif key == "sender_matches":
            if not _any(value, lambda v: re.search(str(v), addr, re.IGNORECASE)):
                return False

        elif key == "subject_matches":
            if not _any(value, lambda v: re.search(str(v), subject, re.IGNORECASE)):
                return False

        elif key == "has_attachment":
            has_att = num_att > 0
            if has_att != bool(value):
                return False

        elif key == "older_than_days":
            if msg_time:
                cutoff = datetime.now() - timedelta(days=int(value))
                if msg_time > cutoff.timestamp():
                    return False

        elif key == "unread":
            if bool(unread) != bool(value):
                return False

    return True


def apply_actions(
    client: ProtonMailExt,
    messages: list,
    actions: dict,
    label_map: dict,
    source_folder: str = INBOX,
) -> None:
    """Apply actions to matched messages.

    source_folder is the folder the messages came from; ``move_to`` removes
    that label after filing into the target (so a move out of Archive removes
    Archive, not Inbox).

    ``delete`` moves to Trash rather than hard-deleting, and folder moves are
    recorded in the oplog, so everything a rule does is reversible via
    ``pmo undo``.
    """
    ids = [m.get("ID", "") for m in messages]

    for action, value in actions.items():
        try:
            if action == "delete" and value:
                _move_and_record(
                    client,
                    ids,
                    TRASH,
                    "Moving to Trash",
                    source_folder,
                    f"Rule moved {len(ids)} message(s) to Trash",
                )

            elif action == "archive" and value:
                _move_and_record(
                    client,
                    ids,
                    ARCHIVE,
                    "Archiving",
                    source_folder,
                    f"Rule archived {len(ids)} message(s)",
                )

            elif action == "star" and value:
                _batch_operation(
                    lambda batch: client.set_label_for_messages(STARRED, batch),
                    ids,
                    "Starring",
                )

            elif action == "mark_read" and value:
                _batch_operation(client.mark_messages_as_read, ids, "Marking read")

            elif action == "add_label":
                label_id = _resolve_label(client, value, label_map)
                if label_id:
                    _batch_operation(
                        lambda batch, lid=label_id: client.set_label_for_messages(lid, batch),
                        ids,
                        f"Adding label '{value}'",
                    )

            elif action == "remove_label":
                label_id = label_map.get(value.lower())
                if label_id:
                    _batch_operation(
                        lambda batch, lid=label_id: client.unset_label_for_messages(lid, batch),
                        ids,
                        f"Removing label '{value}'",
                    )

            elif action == "move_to":
                label_id = _resolve_label(client, value, label_map, label_type=LABEL_TYPE_FOLDER)
                if label_id:
                    _move_and_record(
                        client,
                        ids,
                        label_id,
                        f"Moving to '{value}'",
                        source_folder,
                        f"Rule moved {len(ids)} message(s) to '{value}'",
                        unset_source=True,
                    )

        except Exception as e:
            print_error(f"Action '{action}' failed: {e}")


def _move_and_record(
    client: ProtonMailExt,
    ids: list,
    target_label: str,
    verb: str,
    source_folder: str,
    description: str,
    unset_source: bool = False,
) -> None:
    """File messages into target_label and log an undoable operation.

    System folders (Trash/Archive) are exclusive server-side, so only moves
    into custom folders need the explicit unset of the source folder.
    """
    _batch_operation(
        lambda batch: client.set_label_for_messages(target_label, batch),
        ids,
        verb,
    )
    if unset_source:
        source_name = SYSTEM_LABELS.get(source_folder, "source folder")
        _batch_operation(
            lambda batch: client.unset_label_for_messages(source_folder, batch),
            ids,
            f"Removing from {source_name}",
        )
    record_operation(description, ids, added_label=target_label, removed_label=source_folder)


def _resolve_label(
    client: ProtonMailExt,
    name: str,
    label_map: dict,
    label_type: int = LABEL_TYPE_LABEL,
) -> Optional[str]:
    """Resolve a label name to ID, creating it (as label_type) if needed."""
    label_id = label_map.get(name.lower())
    if label_id:
        return label_id

    print_info(f"Creating '{name}'...")
    try:
        from .labels import create_label

        result = create_label(client, name, label_type=label_type)
        if result:
            new_id = result.get("ID", "")
            label_map[name.lower()] = new_id
            return new_id
    except Exception as e:
        print_error(f"Could not create label '{name}': {e}")

    return None


def _batch_operation(func, ids: list, description: str) -> None:
    """Run a function in batches; one failed batch doesn't stop the rest."""
    failed = batch_apply(func, ids, description, progress=False)
    print_success(f"  {description}: {len(ids) - failed} message(s)")
