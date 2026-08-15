"""Click CLI commands for ProtonMail Organizer."""

from __future__ import annotations

from datetime import datetime, timedelta

import click

from .auth import get_authenticated_client, interactive_login, logout, session_status
from .constants import (
    DEFAULT_LABEL_COLOR,
    INBOX,
    LABEL_TYPE_FOLDER,
    LABEL_TYPE_LABEL,
    SPAM,
    TRASH,
)
from .display import print_error


@click.group()
@click.version_option(package_name="protonmail-organizer")
def cli():
    """ProtonMail Organizer - organize your inbox from the command line."""
    pass


# ── Auth ─────────────────────────────────────────────────────────────────────


@cli.group()
def auth():
    """Login, logout, and session management."""
    pass


@auth.command()
def login():
    """Authenticate with ProtonMail."""
    interactive_login()


@auth.command()
def status():
    """Show current session status."""
    session_status()


@auth.command(name="logout")
def auth_logout():
    """Remove saved session."""
    logout()


# ── Messages ─────────────────────────────────────────────────────────────────


@cli.group()
def messages():
    """List, search, read, and count messages."""
    pass


@messages.command(name="list")
@click.option("--folder", default=INBOX, help="Folder/label ID (default: Inbox).")
@click.option("--limit", default=20, help="Number of messages to show.")
@click.option("--page", default=0, help="Page number (0-indexed).")
def messages_list(folder, limit, page):
    """List messages in a folder."""
    client = get_authenticated_client()
    from .messages import list_messages

    list_messages(client, folder, limit, page)


@messages.command()
@click.option("--keyword", "-k", default=None, help="Search term.")
@click.option("--sender", "--from", "sender", default=None, help="Filter by sender.")
@click.option("--to", "recipient", default=None, help="Filter by recipient.")
@click.option("--has-attachments", is_flag=True, default=None, help="Has attachments.")
@click.option("--days", default=None, type=int, help="Only messages from last N days.")
@click.option("--folder", default=None, help="Folder/label ID to search in.")
@click.option("--limit", default=20, help="Max results.")
def search(keyword, sender, recipient, has_attachments, days, folder, limit):
    """Search messages with filters."""
    client = get_authenticated_client()
    from .messages import search_messages

    begin = None
    if days:
        begin = int((datetime.now() - timedelta(days=days)).timestamp())
    search_messages(
        client,
        keyword=keyword,
        sender=sender,
        recipient=recipient,
        begin=begin,
        has_attachments=has_attachments or None,
        label_id=folder,
        limit=limit,
    )


@messages.command()
@click.argument("message_id")
def read(message_id):
    """Read a message by ID."""
    client = get_authenticated_client()
    from .messages import read_message

    read_message(client, message_id)


@messages.command()
@click.option("--folder", default=None, help="Folder/label ID.")
def count(folder):
    """Show message counts by folder."""
    client = get_authenticated_client()
    from .messages import count_messages

    count_messages(client, folder)


# ── Labels ───────────────────────────────────────────────────────────────────


@cli.group()
def labels():
    """List, create, delete, and apply labels."""
    pass


@labels.command(name="list")
@click.option(
    "--type",
    "label_type",
    type=click.Choice(["all", "labels", "folders", "system"]),
    default="all",
    help="Filter by type.",
)
def labels_list(label_type):
    """List labels and folders."""
    client = get_authenticated_client()
    from .labels import list_labels

    list_labels(client, label_type)


@labels.command()
@click.option("--name", required=True, help="Label name.")
@click.option("--color", default=DEFAULT_LABEL_COLOR, help="Hex color (e.g. #7272a7).")
@click.option("--folder", is_flag=True, help="Create as folder instead of label.")
def create(name, color, folder):
    """Create a new label or folder."""
    client = get_authenticated_client()
    from .labels import create_label

    label_type = LABEL_TYPE_FOLDER if folder else LABEL_TYPE_LABEL
    create_label(client, name, color, label_type)


@labels.command()
@click.argument("label_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def delete(label_id, yes):
    """Delete a label or folder by ID."""
    client = get_authenticated_client()
    from .labels import delete_label

    delete_label(client, label_id, skip_confirm=yes)


@labels.command()
@click.argument("label_id")
@click.option("--messages", "message_ids", multiple=True, help="Message IDs to label.")
@click.option("--remove", is_flag=True, help="Remove label instead of applying.")
def apply(label_id, message_ids, remove):
    """Apply or remove a label from messages."""
    if not message_ids:
        print_error("Provide at least one --messages ID.")
        return
    client = get_authenticated_client()
    from .labels import apply_label

    apply_label(client, label_id, list(message_ids), remove=remove)


# ── Cleanup ──────────────────────────────────────────────────────────────────


@cli.group()
def cleanup():
    """Bulk delete, archive, and cleanup operations."""
    pass


@cleanup.command()
@click.option("--days", required=True, type=int, help="Delete messages older than N days.")
@click.option("--folder", default=INBOX, help="Folder to clean (default: Inbox).")
@click.option("--dry-run", is_flag=True, help="Preview without deleting.")
@click.option("--permanent", is_flag=True, help="Permanently delete instead of moving to Trash.")
def old(days, folder, dry_run, permanent):
    """Move messages older than N days to Trash (or --permanent)."""
    client = get_authenticated_client()
    from .cleanup import delete_old_messages

    delete_old_messages(client, days, folder, dry_run, permanent)


@cleanup.command()
@click.option("--pattern", required=True, help="Sender email/domain pattern.")
@click.option("--dry-run", is_flag=True, help="Preview without archiving.")
def sender(pattern, dry_run):
    """Archive all messages from a sender pattern."""
    client = get_authenticated_client()
    from .cleanup import archive_by_sender

    archive_by_sender(client, pattern, dry_run)


@cleanup.command()
@click.option("--dry-run", is_flag=True, help="Preview without acting.")
@click.option("--delete", "do_delete", is_flag=True, help="Remove instead of just listing.")
@click.option("--permanent", is_flag=True, help="Permanently delete instead of moving to Trash.")
def newsletters(dry_run, do_delete, permanent):
    """Detect and optionally remove newsletter messages (to Trash by default)."""
    client = get_authenticated_client()
    from .cleanup import handle_newsletters

    handle_newsletters(client, dry_run, do_delete, permanent)


@cleanup.command(name="empty-trash")
@click.option("--spam", "include_spam", is_flag=True, help="Also empty Spam.")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def empty_trash(include_spam, yes):
    """Empty Trash (and optionally Spam)."""
    client = get_authenticated_client()
    from .cleanup import empty_folder

    empty_folder(client, TRASH, skip_confirm=yes)
    if include_spam:
        empty_folder(client, SPAM, skip_confirm=yes)


@cleanup.command()
@click.option("--limit", default=50, help="Max messages to scan.")
def unsubscribe(limit):
    """Find messages with unsubscribe links."""
    client = get_authenticated_client()
    from .cleanup import find_unsubscribe_links

    find_unsubscribe_links(client, limit)


# ── Rules ────────────────────────────────────────────────────────────────────


@cli.group()
def rules():
    """YAML-based rule engine for auto-organizing."""
    pass


@rules.command(name="run")
@click.option("--dry-run", is_flag=True, help="Show what would happen without applying.")
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
@click.option("--folder", default=INBOX, help="Folder/label ID to run against (default: Inbox).")
def rules_run(dry_run, rules_file, folder):
    """Run rules against a folder (default: your inbox)."""
    client = get_authenticated_client()
    from .rules import run_rules

    run_rules(client, rules_file, dry_run, folder)


@rules.command(name="list")
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
def rules_list(rules_file):
    """List configured rules."""
    from .rules import list_rules

    list_rules(rules_file)


@rules.command()
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
def validate(rules_file):
    """Validate rules file syntax and references."""
    client = get_authenticated_client()
    from .rules import validate_rules

    validate_rules(client, rules_file)


@rules.command()
def init():
    """Create an example rules file."""
    from .rules import init_rules

    init_rules()


@rules.command(name="stats")
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
@click.option("--limit", default=200, help="Max messages to scan.")
def rules_stats(rules_file, limit):
    """Show rule coverage stats and unmatched senders. (experimental)"""
    client = get_authenticated_client()
    from .rule_analytics import rule_stats

    rule_stats(client, rules_file, limit)


@rules.command()
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
@click.option("--limit", default=200, help="Max messages to scan.")
def suggest(rules_file, limit):
    """Suggest new rules based on unmatched messages. (experimental)"""
    client = get_authenticated_client()
    from .rule_analytics import suggest_rules

    suggest_rules(client, rules_file, limit)


# ── Filters (Server-Side Sieve) ─────────────────────────────────────────────


@cli.group()
def filters():
    """Server-side Sieve filter management."""
    pass


@filters.command(name="list")
def filters_list():
    """Show active server-side filters."""
    client = get_authenticated_client()
    from .filters import list_filters

    list_filters(client)


@filters.command()
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
def push(rules_file):
    """Compile YAML rules to Sieve and push to ProtonMail."""
    client = get_authenticated_client()
    from .filters import push_rules

    push_rules(client, rules_file)


@filters.command()
def pull():
    """Download server-side filters and show Sieve code."""
    client = get_authenticated_client()
    from .filters import pull_filters

    pull_filters(client)


@filters.command(name="delete")
@click.argument("filter_id", required=False, default=None)
@click.option("--all", "delete_all", is_flag=True, help="Delete all server-side filters.")
def filters_delete(filter_id, delete_all):
    """Remove server-side filters."""
    if not filter_id and not delete_all:
        print_error("Provide a filter ID or use --all.")
        return
    client = get_authenticated_client()
    from .filters import delete_filter

    delete_filter(client, filter_id, delete_all)


@filters.command()
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
def preview(rules_file):
    """Show compiled Sieve without pushing."""
    from .filters import preview_sieve

    preview_sieve(rules_file)


@filters.command()
@click.argument("filter_id")
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
@click.option("--name", default=None, help="New filter name.")
def update(filter_id, rules_file, name):
    """Update an existing server-side filter with recompiled rules."""
    client = get_authenticated_client()
    from .display import print_error as _print_error
    from .display import print_success as _print_success
    from .filters import _compile_from_file

    sieve = _compile_from_file(rules_file, client=client)
    if not sieve:
        return
    try:
        client.update_filter(filter_id, sieve, name=name)
        _print_success(f"Updated filter {filter_id}")
    except Exception as e:
        _print_error(f"Failed to update filter: {e}")


# ── Respond (AI Draft Replies) ───────────────────────────────────────────────


@cli.group()
def respond():
    """AI-powered draft reply generator."""
    pass


_BACKEND_OPTION = click.option(
    "--backend",
    type=click.Choice(["anthropic", "local"]),
    default=None,
    help="AI backend (default: PMO_AI_BACKEND). 'local' uses an OpenAI-compatible server.",
)


@respond.command(name="to")
@click.argument("message_id")
@click.option("--context", "-c", default=None, help="Instructions for the reply.")
@click.option("--model", default=None, help="Model override (default: PMO_AI_MODEL).")
@_BACKEND_OPTION
def respond_to(message_id, context, model, backend):
    """Generate a draft reply for a specific message."""
    client = get_authenticated_client()
    from .responder import respond_to_message

    respond_to_message(client, message_id, context, model, backend)


@respond.command(name="interactive")
@click.option("--model", default=None, help="Model override (default: PMO_AI_MODEL).")
@_BACKEND_OPTION
def respond_interactive(model, backend):
    """Pick a message from inbox, then draft a reply."""
    client = get_authenticated_client()
    from .responder import respond_interactive as _respond_interactive

    _respond_interactive(client, model, backend)


@respond.command()
@click.option("--refresh", is_flag=True, help="Re-analyze sent emails and rebuild profile.")
@click.option("--samples", default=50, help="Number of sent emails to analyze.")
def profile(refresh, samples):
    """Show or rebuild your writing style profile. (experimental)"""
    if refresh:
        client = get_authenticated_client()
        from .style_profile import refresh_profile

        refresh_profile(client, samples)
    else:
        from .style_profile import show_profile

        show_profile()


# ── Templates ────────────────────────────────────────────────────────────────


@cli.group()
def templates():
    """Reusable email reply templates. (experimental)"""
    pass


@templates.command(name="list")
def templates_list():
    """List all saved templates."""
    from .templates import list_templates

    list_templates()


@templates.command(name="create")
@click.argument("name")
@click.option("--body", "-b", default=None, help="Template body (opens editor if omitted).")
def templates_create(name, body):
    """Create a new reply template."""
    from .templates import create_template

    create_template(name, body)


@templates.command()
@click.argument("name")
def show(name):
    """Show a template's full content."""
    from .templates import show_template

    show_template(name)


@templates.command()
@click.argument("name")
def edit(name):
    """Edit an existing template."""
    from .templates import edit_template

    edit_template(name)


@templates.command(name="delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def templates_delete(name, yes):
    """Delete a template."""
    from .templates import delete_template

    delete_template(name, skip_confirm=yes)


@templates.command()
@click.argument("template_name")
@click.argument("message_id")
def use(template_name, message_id):
    """Apply a template as a reply to a message."""
    client = get_authenticated_client()
    from .templates import use_template

    use_template(client, template_name, message_id)


# ── Undo ─────────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--list", "show_list", is_flag=True, help="Show the operation history instead.")
def undo(show_list):
    """Reverse the most recent bulk operation (cleanup or rule archive / move / trash)."""
    if show_list:
        from .oplog import list_operations

        list_operations()
        return
    client = get_authenticated_client()
    from .oplog import undo_last

    undo_last(client)


# ── Watch Mode ───────────────────────────────────────────────────────────────


@cli.command()
@click.option("--interval", default=60, help="Seconds between polls (default: 60).")
@click.option("--file", "rules_file", default=None, help="Path to rules YAML.")
def watch(interval, rules_file):
    """Watch inbox and auto-apply rules continuously."""
    client = get_authenticated_client()
    from .watch import watch_inbox

    watch_inbox(client, interval, rules_file)


# ── Digest ───────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--days", default=1, help="Number of days to summarize (default: 1).")
def digest(days):
    """Show a summary digest of recent email activity."""
    client = get_authenticated_client()
    from .messages import digest_report

    digest_report(client, days)


# ── Stats ────────────────────────────────────────────────────────────────────


@cli.command()
def stats():
    """Show account overview and message stats."""
    client = get_authenticated_client()
    from .messages import show_stats

    show_stats(client)


# ── Organize (Interactive) ───────────────────────────────────────────────────


@cli.command()
def organize():
    """Interactive menu-driven organizer."""
    client = get_authenticated_client()
    from .interactive import interactive_menu

    interactive_menu(client)
