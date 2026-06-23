"""Email template management — create, edit, and apply reusable reply templates.

Templates are stored as JSON at ~/.config/protonmail-organizer/templates.json
with restrictive file permissions (0o600). They support placeholder variables
({sender_first}, {sender_name}, {sender_email}, {subject}) that are filled in
when a template is applied to a message.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from .client_ext import ProtonMailExt
from .config import CONFIG_DIR, ensure_config_dir
from .display import console, print_error, print_info, print_success, print_warning

TEMPLATES_FILE = CONFIG_DIR / "templates.json"

# Allowed placeholders in template bodies
PLACEHOLDERS = {
    "{sender_first}": "First name of the sender",
    "{sender_name}": "Full name of the sender",
    "{sender_email}": "Email address of the sender",
    "{subject}": "Subject line of the original message",
}

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")


# --- Internal I/O Helpers ---


def _load_templates() -> dict:
    """Load templates from the JSON file. Returns empty dict if missing or invalid."""
    if not TEMPLATES_FILE.exists():
        return {}
    try:
        with open(TEMPLATES_FILE) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _save_templates(templates: dict) -> None:
    """Save templates dict to JSON with restrictive permissions."""
    ensure_config_dir()
    with open(TEMPLATES_FILE, "w") as f:
        json.dump(templates, f, indent=2)
    os.chmod(TEMPLATES_FILE, 0o600)


# --- Validation ---


def _validate_name(name: str) -> Optional[str]:
    """Validate a template name. Returns an error message or None if valid."""
    if not name:
        return "Template name cannot be empty."
    if not _NAME_PATTERN.match(name):
        return (
            "Template name must start with a letter or digit and contain "
            "only alphanumeric characters and hyphens."
        )
    return None


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# --- Editor ---


def _open_in_editor(initial_text: str = "") -> Optional[str]:
    """Open text in $EDITOR or fall back to inline input.

    Returns the edited text, or None if the user provided empty content.
    """
    editor = os.environ.get("EDITOR", "")

    if editor:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write(initial_text)
                tmp_path = f.name

            subprocess.run([editor, tmp_path], check=True)

            with open(tmp_path) as f:
                edited = f.read()

            if edited.strip():
                return edited.strip()
            else:
                print_warning("Empty content, operation cancelled.")
                return None
        except Exception as e:
            print_error(f"Editor failed: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # Fallback: inline input
    console.print("[dim]Enter template body (empty line + Enter to finish):[/dim]")
    lines = []
    while True:
        line = console.input("")
        if line == "":
            break
        lines.append(line)

    if lines:
        return "\n".join(lines)
    return None


# --- Public API ---


def list_templates() -> None:
    """Display all saved templates in a Rich table."""
    templates = _load_templates()

    if not templates:
        print_info("No templates saved. Create one with: pmo template create <name>")
        return

    table = Table(title="Email Templates", show_lines=False, expand=True)
    table.add_column("Name", style="cyan", max_width=25)
    table.add_column("Body Preview", style="white")
    table.add_column("Uses", justify="right", style="yellow", width=6)
    table.add_column("Last Used", style="green", width=12)

    for tpl in templates.values():
        name = tpl.get("name", "?")
        body = tpl.get("body", "")
        preview = _truncate(body.replace("\n", " "), 60)
        use_count = str(tpl.get("use_count", 0))
        last_used = tpl.get("last_used")
        if last_used:
            try:
                dt = datetime.fromisoformat(last_used)
                last_used_str = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                last_used_str = ""
        else:
            last_used_str = "never"

        table.add_row(name, preview, use_count, last_used_str)

    console.print(table)


def create_template(name: str, body: Optional[str] = None) -> None:
    """Create a new email template.

    Args:
        name: Template name (alphanumeric + hyphens).
        body: Template body text. If None, opens $EDITOR or inline input.
    """
    # Validate name
    error = _validate_name(name)
    if error:
        print_error(error)
        return

    # Check for duplicates
    templates = _load_templates()
    if name in templates:
        print_error(f"Template '{name}' already exists. Use edit to modify it.")
        return

    # Get body content
    if body is None:
        console.print(f"[dim]Available placeholders: {', '.join(PLACEHOLDERS.keys())}[/dim]")
        body = _open_in_editor()

    if not body or not body.strip():
        print_error("Template body cannot be empty.")
        return

    templates[name] = {
        "name": name,
        "subject_prefix": "Re: ",
        "body": body,
        "created": datetime.now().isoformat(),
        "last_used": None,
        "use_count": 0,
    }

    _save_templates(templates)
    print_success(f"Template '{name}' created.")


def show_template(name: str) -> None:
    """Display a single template's full content in a Rich Panel.

    Args:
        name: Template name to display.
    """
    templates = _load_templates()
    tpl = templates.get(name)

    if not tpl:
        print_error(f"Template '{name}' not found.")
        _suggest_templates(templates)
        return

    created = tpl.get("created", "")
    last_used = tpl.get("last_used") or "never"
    use_count = tpl.get("use_count", 0)
    body = tpl.get("body", "")
    subject_prefix = tpl.get("subject_prefix", "Re: ")

    content = (
        f"[cyan]Name:[/cyan] {name}\n"
        f"[cyan]Subject prefix:[/cyan] {subject_prefix}\n"
        f"[cyan]Created:[/cyan] {created}\n"
        f"[cyan]Last used:[/cyan] {last_used}\n"
        f"[cyan]Use count:[/cyan] {use_count}\n"
        f"\n[bold]Body:[/bold]\n{body}"
    )

    console.print(Panel(content, title=f"Template: {name}", border_style="blue"))


def edit_template(name: str) -> None:
    """Open an existing template in $EDITOR for editing.

    Args:
        name: Template name to edit.
    """
    templates = _load_templates()
    tpl = templates.get(name)

    if not tpl:
        print_error(f"Template '{name}' not found.")
        _suggest_templates(templates)
        return

    current_body = tpl.get("body", "")
    console.print(
        f"[dim]Editing template '{name}'. "
        f"Available placeholders: {', '.join(PLACEHOLDERS.keys())}[/dim]"
    )

    new_body = _open_in_editor(current_body)

    if new_body is None:
        print_warning("No changes made.")
        return

    if new_body == current_body:
        print_info("No changes detected.")
        return

    tpl["body"] = new_body
    _save_templates(templates)
    print_success(f"Template '{name}' updated.")


def delete_template(name: str, skip_confirm: bool = False) -> None:
    """Delete a template with confirmation.

    Args:
        name: Template name to delete.
        skip_confirm: If True, skip the confirmation prompt.
    """
    templates = _load_templates()

    if name not in templates:
        print_error(f"Template '{name}' not found.")
        _suggest_templates(templates)
        return

    if not skip_confirm:
        answer = (
            console.input(f"[bold red]Delete template '{name}'? (y/N): [/bold red]").strip().lower()
        )
        if answer != "y":
            print_warning("Cancelled.")
            return

    del templates[name]
    _save_templates(templates)
    print_success(f"Template '{name}' deleted.")


def use_template(
    client: ProtonMailExt,
    template_name: str,
    message_id: str,
) -> None:
    """Apply a template as a reply to a message.

    Reads the original message to extract sender info, fills in template
    placeholders, shows the filled draft, and lets the user send, edit, or cancel.

    Args:
        client: Authenticated ProtonMail client.
        template_name: Name of the template to use.
        message_id: ID of the message to reply to.
    """
    # Load template
    templates = _load_templates()
    tpl = templates.get(template_name)

    if not tpl:
        print_error(f"Template '{template_name}' not found.")
        _suggest_templates(templates)
        return

    # Read the original message
    try:
        msg = client.read_message(message_id)
    except Exception as e:
        print_error(f"Failed to read message {message_id}: {e}")
        return

    # Extract sender info
    sender = getattr(msg, "sender", None)
    sender_name = sender.name if sender else ""
    sender_email = sender.address if sender else ""
    sender_first = (
        sender_name.split()[0]
        if sender_name and sender_name.split()
        else sender_email.split("@")[0]
        if sender_email
        else ""
    )
    subject = msg.subject if hasattr(msg, "subject") else ""

    # Show original message context
    sender_str = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    console.print(
        Panel(
            f"[cyan]From:[/cyan] {sender_str}\n[cyan]Subject:[/cyan] {subject}",
            title="Replying to",
            border_style="blue",
        )
    )

    # Fill placeholders
    filled_body = tpl["body"]
    filled_body = filled_body.replace("{sender_first}", sender_first)
    filled_body = filled_body.replace("{sender_name}", sender_name)
    filled_body = filled_body.replace("{sender_email}", sender_email)
    filled_body = filled_body.replace("{subject}", subject)

    # Build reply subject
    subject_prefix = tpl.get("subject_prefix", "Re: ")
    reply_subject = subject
    if subject_prefix and not reply_subject.lower().startswith(subject_prefix.lower().strip()):
        reply_subject = f"{subject_prefix}{reply_subject}"

    # Interactive review loop
    current_draft = filled_body

    while True:
        console.print(
            Panel(
                current_draft,
                title=f"Template Reply: {template_name}",
                border_style="green",
            )
        )

        console.print("[bold][S][/bold]end  [bold][E][/bold]dit  [bold][C][/bold]ancel")
        action = console.input("[bold]Action: [/bold]").strip().lower()

        if action in ("s", "send"):
            _send_template_reply(client, msg, current_draft, reply_subject)
            # Update usage stats
            tpl["use_count"] = tpl.get("use_count", 0) + 1
            tpl["last_used"] = datetime.now().isoformat()
            _save_templates(templates)
            break

        elif action in ("e", "edit"):
            edited = _open_in_editor(current_draft)
            if edited is not None:
                current_draft = edited
                print_success("Draft updated.")

        elif action in ("c", "cancel"):
            print_warning("Cancelled.")
            break

        else:
            print_warning("Unknown action. Use S/E/C.")


# --- Private Helpers ---


def _send_template_reply(
    client: ProtonMailExt,
    original_msg,
    draft_body: str,
    subject: str,
) -> None:
    """Send the filled template as a reply to the original message."""
    sender = getattr(original_msg, "sender", None)
    if not sender:
        print_error("Cannot determine recipient from original message.")
        return

    recipient_addr = sender.address

    try:
        from protonmail import ProtonMail

        message = ProtonMail.create_message(
            recipients=[recipient_addr],
            subject=subject,
            body=draft_body,
        )
        client.send_message(message)
        print_success(f"Reply sent to {recipient_addr}")
    except Exception as e:
        print_error(f"Failed to send reply: {e}")


def _suggest_templates(templates: dict) -> None:
    """Print available template names as a hint when a lookup fails."""
    if templates:
        names = ", ".join(sorted(templates.keys()))
        print_info(f"Available templates: {names}")
