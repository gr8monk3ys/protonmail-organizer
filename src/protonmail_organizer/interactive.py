"""Interactive menu-driven organizer mode."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from .client_ext import ProtonMailExt
from .constants import INBOX, SPAM, TRASH
from .display import print_error, print_info, print_warning

console = Console()

MENU = """\
[bold cyan]ProtonMail Organizer[/bold cyan]

  [1] List inbox messages
  [2] Search messages
  [3] List labels & folders
  [4] Create label/folder
  [5] Message counts
  [6] Cleanup old messages
  [7] Archive by sender
  [8] Detect newsletters
  [9] Empty trash
  [10] Run rules
  [11] Account stats
  [12] Digest report
  [13] Preview Sieve filters
  [14] AI draft reply
  [15] Find unsubscribe links
  [16] Rule coverage stats
  [17] Suggest new rules
  [18] List templates
  [19] Use template reply

  [q] Quit
"""


def interactive_menu(client: ProtonMailExt) -> None:
    """Run the interactive menu loop."""
    while True:
        console.print(Panel(MENU, border_style="blue"))
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
    """Dispatch menu choice to the appropriate function."""

    if choice == "1":
        from .messages import list_messages
        folder = console.input("Folder ID [0=Inbox]: ").strip() or INBOX
        list_messages(client, folder)

    elif choice == "2":
        from .messages import search_messages
        keyword = console.input("Search keyword (or empty): ").strip() or None
        sender = console.input("Sender filter (or empty): ").strip() or None
        search_messages(client, keyword=keyword, sender=sender)

    elif choice == "3":
        from .labels import list_labels
        list_labels(client, "all")

    elif choice == "4":
        from .labels import create_label
        name = console.input("Label name: ").strip()
        if not name:
            print_warning("Name required.")
            return
        is_folder = console.input("Create as folder? (y/N): ").strip().lower() == "y"
        from .constants import LABEL_TYPE_FOLDER, LABEL_TYPE_LABEL, DEFAULT_LABEL_COLOR
        label_type = LABEL_TYPE_FOLDER if is_folder else LABEL_TYPE_LABEL
        create_label(client, name, DEFAULT_LABEL_COLOR, label_type)

    elif choice == "5":
        from .messages import count_messages
        count_messages(client)

    elif choice == "6":
        from .cleanup import delete_old_messages
        days_str = console.input("Delete messages older than N days: ").strip()
        try:
            days = int(days_str)
        except ValueError:
            print_error("Invalid number.")
            return
        dry = console.input("Dry run? (Y/n): ").strip().lower() != "n"
        delete_old_messages(client, days, INBOX, dry)

    elif choice == "7":
        from .cleanup import archive_by_sender
        pattern = console.input("Sender pattern (email or domain): ").strip()
        if not pattern:
            print_warning("Pattern required.")
            return
        dry = console.input("Dry run? (Y/n): ").strip().lower() != "n"
        archive_by_sender(client, pattern, dry)

    elif choice == "8":
        from .cleanup import handle_newsletters
        handle_newsletters(client, dry_run=True)

    elif choice == "9":
        from .cleanup import empty_folder
        empty_folder(client, TRASH)
        also_spam = console.input("Also empty Spam? (y/N): ").strip().lower() == "y"
        if also_spam:
            empty_folder(client, SPAM)

    elif choice == "10":
        from .rules import run_rules
        dry = console.input("Dry run? (Y/n): ").strip().lower() != "n"
        run_rules(client, dry_run=dry)

    elif choice == "11":
        from .messages import show_stats
        show_stats(client)

    elif choice == "12":
        from .messages import digest_report
        days_str = console.input("Days to summarize [1]: ").strip() or "1"
        try:
            days = int(days_str)
        except ValueError:
            print_error("Invalid number.")
            return
        digest_report(client, days)

    elif choice == "13":
        from .filters import preview_sieve
        preview_sieve()

    elif choice == "14":
        from .responder import respond_interactive
        respond_interactive(client)

    elif choice == "15":
        from .cleanup import find_unsubscribe_links
        find_unsubscribe_links(client)

    elif choice == "16":
        from .rule_analytics import rule_stats
        rule_stats(client)

    elif choice == "17":
        from .rule_analytics import suggest_rules
        suggest_rules(client)

    elif choice == "18":
        from .templates import list_templates
        list_templates()

    elif choice == "19":
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

    else:
        print_warning(f"Unknown option: {choice}")
