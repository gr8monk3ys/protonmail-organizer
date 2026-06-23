"""YAML-based rule engine for auto-organizing messages."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

from .client_ext import ProtonMailExt
from .config import RULES_FILE, ensure_config_dir
from .constants import (
    ARCHIVE,
    BATCH_DELAY_SECONDS,
    BATCH_SIZE,
    FREE_PLAN_MAX_LABELS,
    INBOX,
    LABEL_TYPE_FOLDER,
    LABEL_TYPE_LABEL,
    STARRED,
    SYSTEM_LABELS,
)
from .display import (
    console,
    message_table,
    print_error,
    print_info,
    print_success,
    print_warning,
)

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


def _load_rules(rules_file: Optional[str] = None) -> list:
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
    rules = _load_rules(rules_file)
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
    rules = _load_rules(rules_file)
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

        # Check label references
        for action_key in ("add_label", "remove_label", "move_to"):
            target = actions.get(action_key)
            if target and target.lower() not in all_names:
                referenced_new_labels.add(target)

    # Check free-plan limits for new labels
    new_label_count = len(referenced_new_labels)
    if new_label_count > 0:
        available_labels = FREE_PLAN_MAX_LABELS - len(user_labels)
        if new_label_count > available_labels:
            print_warning(
                f"Rules reference {new_label_count} label(s) that don't exist yet: "
                f"{referenced_new_labels}. Only {available_labels} more can be "
                f"created on the free plan."
            )
        else:
            print_info(
                f"Rules reference {new_label_count} new label(s): {referenced_new_labels}. "
                f"They will be created when rules run."
            )

    if valid:
        print_success(f"All {len(rules)} rule(s) are valid.")
    return valid


def run_rules(
    client: ProtonMailExt,
    rules_file: Optional[str] = None,
    dry_run: bool = False,
    folder: str = INBOX,
) -> None:
    """Run rules against the messages in a folder (default: Inbox)."""
    rules = _load_rules(rules_file)
    if not rules:
        return

    folder_name = SYSTEM_LABELS.get(folder, folder)
    print_info(f"Fetching {folder_name} messages...")
    messages = client.search_messages_all(label_id=folder)

    if not messages:
        print_warning(f"No messages in {folder_name}.")
        return

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

        matched = [m for m in messages if _matches_conditions(m, conditions)]
        if not matched:
            continue

        total_matched += len(matched)
        console.print(f"\n[cyan]Rule '{name}':[/cyan] matched {len(matched)} message(s)")

        if dry_run:
            console.print(
                message_table(
                    matched[:10],
                    title=f"[DRY RUN] Would apply: {actions}",
                )
            )
            if len(matched) > 10:
                console.print(f"[dim]  ...and {len(matched) - 10} more[/dim]")
            continue

        _apply_actions(client, matched, actions, label_map, source_folder=folder)

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


def _matches_conditions(msg: dict, conditions: dict) -> bool:
    """Check if a message matches all conditions (AND across keys).

    A condition value may be a scalar or a list; a list matches if ANY of its
    values match (OR within a single condition).
    """
    sender = msg.get("Sender", {})
    addr = sender.get("Address", "") if isinstance(sender, dict) else ""
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


def _apply_actions(
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
    """
    ids = [m.get("ID", "") for m in messages]
    source_name = SYSTEM_LABELS.get(source_folder, "source folder")

    for action, value in actions.items():
        try:
            if action == "delete" and value:
                _batch_operation(client.delete_messages, ids, "Deleting")

            elif action == "archive" and value:
                _batch_operation(
                    lambda batch: client.set_label_for_messages(ARCHIVE, batch),
                    ids,
                    "Archiving",
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
                label_id = _resolve_label(client, value, label_map)
                if label_id:
                    # File into the target, then remove from the source folder.
                    _batch_operation(
                        lambda batch, lid=label_id: client.set_label_for_messages(lid, batch),
                        ids,
                        f"Moving to '{value}'",
                    )
                    _batch_operation(
                        lambda batch, sid=source_folder: client.unset_label_for_messages(
                            sid, batch
                        ),
                        ids,
                        f"Removing from {source_name}",
                    )

        except Exception as e:
            print_error(f"Action '{action}' failed: {e}")


def _resolve_label(
    client: ProtonMailExt,
    name: str,
    label_map: dict,
) -> Optional[str]:
    """Resolve a label name to ID, creating it if needed."""
    label_id = label_map.get(name.lower())
    if label_id:
        return label_id

    # Try to create the label
    print_info(f"Creating label '{name}'...")
    try:
        from .labels import create_label

        result = create_label(client, name)
        if result:
            new_id = result.get("ID", "")
            label_map[name.lower()] = new_id
            return new_id
    except Exception as e:
        print_error(f"Could not create label '{name}': {e}")

    return None


def _batch_operation(func, ids: list, description: str) -> None:
    """Run a function in batches with delay."""
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i : i + BATCH_SIZE]
        func(batch)
        if i + BATCH_SIZE < len(ids):
            time.sleep(BATCH_DELAY_SECONDS)
    print_success(f"  {description}: {len(ids)} message(s)")
