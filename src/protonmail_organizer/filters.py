"""Server-side Sieve filter CRUD and YAML-to-Sieve compiler.

Compiles YAML rules to ProtonMail-compatible Sieve scripts.
ProtonMail Sieve uses folder *names* (not IDs) in fileinto statements.
Supported extensions: fileinto, imap4flags, mime, foreverypart.
See https://proton.me/support/sieve-advanced-custom-filters
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from rich.syntax import Syntax
from rich.table import Table

from .client_ext import ProtonMailExt
from .config import RULES_FILE
from .display import console, print_error, print_info, print_success, print_warning

# Conditions that require runtime (time-based) — can't be expressed in Sieve
# Note: has_attachment and unread CAN be expressed in Sieve but need special handling
_RUNTIME_ONLY_CONDITIONS = {"older_than_days", "sender_matches", "subject_matches"}


def _sieve_quote(value) -> str:
    """Escape a value for safe interpolation inside a Sieve double-quoted string."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _as_list(value) -> list:
    """Normalize a scalar or list condition value into a list."""
    return value if isinstance(value, list) else [value]


def list_filters(client: ProtonMailExt) -> None:
    """Display active server-side filters in a Rich table."""
    try:
        filters = client.get_filters()
    except Exception as e:
        print_error(f"Failed to fetch filters: {e}")
        print_info("The filter API may not be available on your account.")
        return

    if not filters:
        print_warning("No server-side filters found.")
        return

    table = Table(title="Server-Side Filters", show_lines=False)
    table.add_column("ID", style="dim", max_width=20)
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green", width=10)
    table.add_column("Version", width=8)

    for f in filters:
        status = "enabled" if f.get("Status", 0) == 1 else "disabled"
        status_style = "green" if status == "enabled" else "dim"
        table.add_row(
            str(f.get("ID", "")),
            f.get("Name", ""),
            f"[{status_style}]{status}[/{status_style}]",
            str(f.get("Version", "")),
        )

    console.print(table)
    console.print(f"[dim]{len(filters)} filter(s)[/dim]")


def pull_filters(client: ProtonMailExt) -> None:
    """Download and display server-side filter Sieve code."""
    try:
        filters = client.get_filters()
    except Exception as e:
        print_error(f"Failed to fetch filters: {e}")
        return

    if not filters:
        print_warning("No server-side filters found.")
        return

    for f in filters:
        name = f.get("Name", "Unnamed")
        sieve = f.get("Sieve", "")
        fid = f.get("ID", "")

        console.print(f"\n[bold cyan]Filter: {name}[/bold cyan] [dim](ID: {fid})[/dim]")
        if sieve:
            console.print(Syntax(sieve, "text", theme="monokai", line_numbers=True))
        else:
            print_warning("  (no Sieve code)")


def preview_sieve(rules_file: Optional[str] = None) -> str:
    """Compile YAML rules to Sieve and display without pushing."""
    sieve = _compile_from_file(rules_file)
    if sieve:
        console.print(Syntax(sieve, "text", theme="monokai", line_numbers=True))
    return sieve


def probe_filter_api(client: ProtonMailExt) -> bool:
    """Test whether the filter API endpoints are accessible on this account.

    Returns True if the GET filters endpoint works.
    """
    try:
        client.get_filters()
        return True
    except Exception:
        return False


def push_rules(client: ProtonMailExt, rules_file: Optional[str] = None) -> None:
    """Compile YAML rules to Sieve and push as a server-side filter."""
    # Probe the API first
    print_info("Probing filter API...")
    if not probe_filter_api(client):
        print_error("Filter API is not accessible on your account.")
        print_info("This may require a paid ProtonMail plan, or the API may have changed.")
        print_info("You can still use 'pmo filters preview' to see the compiled Sieve,")
        print_info("then paste it manually in Settings > Filters > Add Sieve filter.")
        return

    sieve = _compile_from_file(rules_file, client=client)
    if not sieve:
        return

    console.print(Syntax(sieve, "text", theme="monokai", line_numbers=True))

    confirm = (
        console.input("\n[yellow]Push this Sieve filter to ProtonMail? (y/N): [/yellow]")
        .strip()
        .lower()
    )
    if confirm != "y":
        print_warning("Cancelled.")
        return

    try:
        result = client.create_filter("PMO Auto-Rules", sieve)
        fid = result.get("ID", "")
        print_success(f"Filter created (ID: {fid}). Check Settings > Filters in ProtonMail web.")
    except Exception as e:
        print_error(f"Failed to create filter: {e}")
        _suggest_manual_paste(sieve)


def delete_filter(
    client: ProtonMailExt, filter_id: Optional[str] = None, delete_all: bool = False
) -> None:
    """Delete server-side filters by ID or all."""
    if delete_all:
        try:
            filters = client.get_filters()
        except Exception as e:
            print_error(f"Failed to fetch filters: {e}")
            return

        if not filters:
            print_warning("No filters to delete.")
            return

        confirm = (
            console.input(
                f"[yellow]Delete all {len(filters)} server-side filter(s)? (y/N): [/yellow]"
            )
            .strip()
            .lower()
        )
        if confirm != "y":
            print_warning("Cancelled.")
            return

        for f in filters:
            fid = f.get("ID", "")
            try:
                client.delete_filter(str(fid))
                print_success(f"  Deleted filter {fid}")
            except Exception as e:
                print_error(f"  Failed to delete filter {fid}: {e}")

        return

    if not filter_id:
        print_error("Provide a filter ID or use --all.")
        return

    try:
        client.delete_filter(filter_id)
        print_success(f"Deleted filter {filter_id}")
    except Exception as e:
        print_error(f"Failed to delete filter: {e}")


def compile_rules_to_sieve(rules: list, label_map: dict | None = None) -> str:
    """Convert YAML rules to a single Sieve script.

    Args:
        rules: List of rule dicts from YAML.
        label_map: Optional label name -> folder name mapping for move_to targets.

    Returns:
        Compiled Sieve script as a string.
    """
    sieve_rules = []
    skipped = []
    needs_fileinto = False
    needs_imap4flags = False
    needs_mime = False

    for rule in rules:
        name = rule.get("name", "Unnamed rule")
        conditions = rule.get("conditions", {})
        actions = rule.get("actions", {})

        # Check if this rule has runtime-only conditions
        runtime_conditions = set(conditions.keys()) & _RUNTIME_ONLY_CONDITIONS
        sieve_conditions = {
            k: v for k, v in conditions.items() if k not in _RUNTIME_ONLY_CONDITIONS
        }

        if runtime_conditions and not sieve_conditions:
            skipped.append((name, runtime_conditions))
            continue

        if runtime_conditions:
            skipped.append((name, f"partial — skipping conditions: {runtime_conditions}"))

        # Build Sieve condition
        sieve_cond, uses_flags_cond, uses_mime_cond = _build_sieve_condition(sieve_conditions)
        if not sieve_cond:
            skipped.append((name, "no convertible conditions"))
            continue

        # Build Sieve actions
        sieve_actions, uses_fileinto, uses_flags_act = _build_sieve_actions(actions)
        if not sieve_actions:
            skipped.append((name, "no convertible actions"))
            continue

        if uses_fileinto:
            needs_fileinto = True
        if uses_flags_cond or uses_flags_act:
            needs_imap4flags = True
        if uses_mime_cond:
            needs_mime = True

        action_block = "\n".join(f"    {a}" for a in sieve_actions)
        sieve_rules.append(f"# {name}\nif {sieve_cond} {{\n{action_block}\n}}")

    if not sieve_rules:
        print_warning("No rules could be converted to Sieve.")
        return ""

    # Build require statement
    requires = []
    if needs_fileinto:
        requires.append('"fileinto"')
    if needs_imap4flags:
        requires.append('"imap4flags"')
    if needs_mime:
        requires.append('"mime"')
        requires.append('"foreverypart"')

    parts = []
    if requires:
        parts.append(f"require [{', '.join(requires)}];")
    parts.append("")
    parts.extend(sieve_rules)
    parts.append("")

    # Show skipped rules
    if skipped:
        print_warning(f"\nSkipped {len(skipped)} rule(s) (runtime-only conditions):")
        for name, reason in skipped:
            print_info(f"  - {name}: {reason}")

    return "\n".join(parts)


def _compile_from_file(
    rules_file: Optional[str] = None, client: Optional[ProtonMailExt] = None
) -> str:
    """Load rules from YAML and compile to Sieve."""
    path = Path(rules_file) if rules_file else RULES_FILE
    if not path.exists():
        print_error(f"Rules file not found: {path}")
        return ""

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "rules" not in data:
        print_error("Invalid rules file: missing 'rules' key.")
        return ""

    rules = data["rules"]

    # Build label map if client available
    label_map = None
    if client:
        label_map = {}
        for label in client.get_all_labels():
            label_map[label.name.lower()] = label.name

    return compile_rules_to_sieve(rules, label_map)


def _build_sieve_condition(conditions: dict) -> tuple[str, bool, bool]:
    """Convert rule conditions to a Sieve test string.

    Returns:
        (test_string, needs_imap4flags, needs_mime)
    """
    tests = []
    needs_imap4flags = False
    needs_mime = False

    # Renderers for value-based conditions. A list value becomes an anyof(...)
    # (OR within the condition); the outer conditions are still AND-ed.
    renderers = {
        "sender_is": lambda v: f'address :is "from" "{_sieve_quote(v)}"',
        "sender_contains": lambda v: f'address :contains "from" "{_sieve_quote(v)}"',
        "sender_domain": lambda v: f'address :matches "from" "*@{_sieve_quote(v)}"',
        "subject_contains": lambda v: f'header :contains "subject" "{_sieve_quote(v)}"',
    }

    for key, value in conditions.items():
        if key in renderers:
            render = renderers[key]
            sub = [render(v) for v in _as_list(value)]
            tests.append(sub[0] if len(sub) == 1 else f"anyof ({', '.join(sub)})")

        elif key == "has_attachment":
            # ProtonMail supports MIME extension for attachment checking
            if value:
                tests.append('header :mime :anychild :type "Content-Disposition" "attachment"')
            else:
                tests.append('not header :mime :anychild :type "Content-Disposition" "attachment"')
            needs_mime = True

        elif key == "unread":
            # Use imap4flags hasflag test — \Seen means read
            if value:
                tests.append('not hasflag "\\\\Seen"')
            else:
                tests.append('hasflag "\\\\Seen"')
            needs_imap4flags = True

    if not tests:
        return "", False, False

    if len(tests) == 1:
        return tests[0], needs_imap4flags, needs_mime

    inner = ", ".join(tests)
    return f"allof ({inner})", needs_imap4flags, needs_mime


def _build_sieve_actions(actions: dict) -> tuple[list[str], bool, bool]:
    """Convert rule actions to Sieve action statements.

    Returns:
        (action_lines, needs_fileinto, needs_imap4flags)
    """
    lines = []
    needs_fileinto = False
    needs_imap4flags = False

    for action, value in actions.items():
        if action == "move_to":
            lines.append(f'fileinto "{value}";')
            needs_fileinto = True

        elif action == "add_label":
            lines.append(f'fileinto "{value}";')
            needs_fileinto = True

        elif action == "mark_read" and value:
            lines.append('addflag "\\\\Seen";')
            needs_imap4flags = True

        elif action == "archive" and value:
            lines.append('fileinto "Archive";')
            needs_fileinto = True

        elif action == "delete" and value:
            lines.append("discard;")

        elif action == "star" and value:
            lines.append('addflag "\\\\Flagged";')
            needs_imap4flags = True

    return lines, needs_fileinto, needs_imap4flags


def _suggest_manual_paste(sieve: str) -> None:
    """Suggest pasting Sieve code manually when the API push fails."""
    print_info("\nYou can still apply this filter manually:")
    print_info("  1. Go to ProtonMail web → Settings → All settings → Filters")
    print_info("  2. Click 'Add sieve filter'")
    print_info("  3. Paste the Sieve code shown above")
    print_info("  4. Save the filter")
    print_info("\nOr copy the compiled Sieve with: pmo filters preview")
