"""Interactive menu-driven organizer mode.

The menu is rendered from MENU_ITEMS, so the text and the dispatch can't
drift apart: adding an entry to the table is the whole change.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from .client_ext import ProtonMailExt
from .constants import INBOX, SPAM, TRASH
from .display import print_error, print_info, print_warning

console = Console()


def _ask_dry_run() -> bool:
    """Consistent dry-run prompt used by every destructive item (default: yes)."""
    return console.input("Dry run? (Y/n): ").strip().lower() != "n"


def _ask_int(prompt: str, default: int | None = None) -> int | None:
    raw = console.input(prompt).strip()
    if not raw and default is not None:
        return default
    try:
        return int(raw)
    except ValueError:
        print_error("Invalid number.")
        return None


# --- Handlers (deferred imports keep startup fast) ---


def _list_inbox(client: ProtonMailExt) -> None:
    from .messages import list_messages

    folder = console.input("Folder ID [0=Inbox]: ").strip() or INBOX
    list_messages(client, folder)


def _search(client: ProtonMailExt) -> None:
    from .messages import search_messages

    keyword = console.input("Search keyword (or empty): ").strip() or None
    sender = console.input("Sender filter (or empty): ").strip() or None
    search_messages(client, keyword=keyword, sender=sender)


def _list_labels(client: ProtonMailExt) -> None:
    from .labels import list_labels

    list_labels(client, "all")


def _create_label(client: ProtonMailExt) -> None:
    from .constants import DEFAULT_LABEL_COLOR, LABEL_TYPE_FOLDER, LABEL_TYPE_LABEL
    from .labels import create_label

    name = console.input("Label name: ").strip()
    if not name:
        print_warning("Name required.")
        return
    is_folder = console.input("Create as folder? (y/N): ").strip().lower() == "y"
    label_type = LABEL_TYPE_FOLDER if is_folder else LABEL_TYPE_LABEL
    create_label(client, name, DEFAULT_LABEL_COLOR, label_type)


def _counts(client: ProtonMailExt) -> None:
    from .messages import count_messages

    count_messages(client)


def _cleanup_old(client: ProtonMailExt) -> None:
    from .cleanup import delete_old_messages

    days = _ask_int("Delete messages older than N days: ")
    if days is None:
        return
    delete_old_messages(client, days, INBOX, _ask_dry_run())


def _archive_by_sender(client: ProtonMailExt) -> None:
    from .cleanup import archive_by_sender

    pattern = console.input("Sender pattern (email or domain): ").strip()
    if not pattern:
        print_warning("Pattern required.")
        return
    archive_by_sender(client, pattern, _ask_dry_run())


def _newsletters(client: ProtonMailExt) -> None:
    from .cleanup import handle_newsletters

    do_delete = console.input("Delete them (otherwise just list)? (y/N): ").strip().lower() == "y"
    dry_run = _ask_dry_run() if do_delete else True
    handle_newsletters(client, dry_run=dry_run, do_delete=do_delete)


def _empty_trash(client: ProtonMailExt) -> None:
    from .cleanup import empty_folder

    empty_folder(client, TRASH)
    if console.input("Also empty Spam? (y/N): ").strip().lower() == "y":
        empty_folder(client, SPAM)


def _run_rules(client: ProtonMailExt) -> None:
    from .rules import run_rules

    run_rules(client, dry_run=_ask_dry_run())


def _undo(client: ProtonMailExt) -> None:
    from .oplog import undo_last

    undo_last(client)


def _stats(client: ProtonMailExt) -> None:
    from .messages import show_stats

    show_stats(client)


def _digest(client: ProtonMailExt) -> None:
    from .messages import digest_report

    days = _ask_int("Days to summarize [1]: ", default=1)
    if days is None:
        return
    digest_report(client, days)


def _preview_sieve(client: ProtonMailExt) -> None:
    from .filters import preview_sieve

    preview_sieve()


def _push_filters(client: ProtonMailExt) -> None:
    from .filters import push_rules

    push_rules(client)


def _ai_reply(client: ProtonMailExt) -> None:
    from .responder import respond_interactive

    respond_interactive(client)


def _unsubscribe_links(client: ProtonMailExt) -> None:
    from .cleanup import find_unsubscribe_links

    find_unsubscribe_links(client)


def _rule_stats(client: ProtonMailExt) -> None:
    from .rule_analytics import rule_stats

    rule_stats(client)


def _suggest_rules(client: ProtonMailExt) -> None:
    from .rule_analytics import suggest_rules

    suggest_rules(client)


def _list_templates(client: ProtonMailExt) -> None:
    from .templates import list_templates

    list_templates()


def _use_template(client: ProtonMailExt) -> None:
    from .templates import use_template

    tpl_name = console.input("Template name: ").strip()
    if not tpl_name:
        print_warning("Template name required.")
        return
    msg_id = console.input("Message ID to reply to: ").strip()
    if not msg_id:
        print_warning("Message ID required.")
        return
    use_template(client, tpl_name, msg_id)


MENU_ITEMS = [
    ("List inbox messages", _list_inbox),
    ("Search messages", _search),
    ("List labels & folders", _list_labels),
    ("Create label/folder", _create_label),
    ("Message counts", _counts),
    ("Cleanup old messages", _cleanup_old),
    ("Archive by sender", _archive_by_sender),
    ("Detect newsletters", _newsletters),
    ("Empty trash", _empty_trash),
    ("Run rules", _run_rules),
    ("Undo last operation", _undo),
    ("Account stats", _stats),
    ("Digest report", _digest),
    ("Preview Sieve filters", _preview_sieve),
    ("Push rules as server-side filter", _push_filters),
    ("AI draft reply", _ai_reply),
    ("Find unsubscribe links", _unsubscribe_links),
    ("Rule coverage stats", _rule_stats),
    ("Suggest new rules", _suggest_rules),
    ("List templates", _list_templates),
    ("Use template reply", _use_template),
]


def _render_menu() -> str:
    items = "\n".join(f"  [{i}] {label}" for i, (label, _) in enumerate(MENU_ITEMS, 1))
    # \[ stops Rich from eating "[q]" as a markup tag
    return f"[bold cyan]ProtonMail Organizer[/bold cyan]\n\n{items}\n\n  \\[q] Quit"


def interactive_menu(client: ProtonMailExt) -> None:
    """Run the interactive menu loop."""
    while True:
        console.print(Panel(_render_menu(), border_style="blue"))
        choice = console.input("[bold]Choose an option: [/bold]").strip().lower()

        if choice in ("q", "quit", "exit"):
            print_info("Goodbye!")
            break

        try:
            _handle_choice(client, choice)
        except KeyboardInterrupt:
            console.print()
            continue
        except Exception as e:
            print_error(f"Error: {e}")

        console.print()


def _handle_choice(client: ProtonMailExt, choice: str) -> None:
    """Dispatch a menu choice to its handler from MENU_ITEMS."""
    if choice.isdigit() and 1 <= int(choice) <= len(MENU_ITEMS):
        MENU_ITEMS[int(choice) - 1][1](client)
    else:
        print_warning(f"Unknown option: {choice}")
