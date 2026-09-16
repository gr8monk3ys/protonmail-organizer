"""Rule analytics: measure rule coverage, find unmatched senders, suggest new rules."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

from rich.panel import Panel
from rich.table import Table

from .client_ext import ProtonMailExt, sender_address
from .config import RULES_FILE
from .constants import INBOX
from .display import (
    console,
    print_info,
    print_success,
    print_warning,
)
from .rules import load_rules, matches_conditions

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_inbox_messages(
    client: ProtonMailExt,
    limit: int = 200,
) -> list:
    """Fetch up to *limit* inbox messages using paginated search."""
    page_size = min(limit, 50)
    messages: list = []
    page = 0

    while len(messages) < limit:
        batch = client.search_messages(
            label_id=INBOX,
            page=page,
            page_size=page_size,
        )
        if not batch:
            break
        messages.extend(batch)
        if len(batch) < page_size:
            break  # last page
        page += 1

    return messages[:limit]


def _extract_sender(msg: dict) -> str:
    """Return the sender address from a message dict (lowercased)."""
    return sender_address(msg).lower()


def _extract_domain(address: str) -> str:
    """Extract the domain part from an email address."""
    if "@" in address:
        return address.split("@", 1)[1]
    return ""


# ---------------------------------------------------------------------------
# rule_stats
# ---------------------------------------------------------------------------


def rule_stats(
    client: ProtonMailExt,
    rules_file: Optional[str] = None,
    limit: int = 200,
) -> None:
    """Analyse inbox messages against YAML rules and display coverage stats.

    Outputs three Rich tables:
    1. Rule Performance   - match count per rule, sorted by frequency
    2. Unmatched Senders  - senders that matched no rules, grouped by domain
    3. Summary panel      - totals and coverage percentage
    """
    rules = load_rules(rules_file)
    if not rules:
        return

    print_info(f"Fetching up to {limit} inbox messages...")
    messages = _fetch_inbox_messages(client, limit=limit)
    if not messages:
        print_warning("No messages in inbox.")
        return

    total = len(messages)
    print_info(f"Evaluating {len(rules)} rule(s) against {total} message(s)...")

    # Per-rule tracking
    rule_matches: dict[str, list[dict]] = {}
    for rule in rules:
        name = rule.get("name", "Unnamed rule")
        rule_matches[name] = []

    # Track which messages matched at least one rule
    matched_ids: set[str] = set()

    for msg in messages:
        msg_id = msg.get("ID", "")
        for rule in rules:
            name = rule.get("name", "Unnamed rule")
            conditions = rule.get("conditions", {})
            if matches_conditions(msg, conditions):
                rule_matches[name].append(msg)
                matched_ids.add(msg_id)

    # --- Rule Performance table ---
    perf_table = Table(
        title="Rule Performance",
        show_lines=False,
        expand=True,
    )
    perf_table.add_column("#", style="dim", width=4)
    perf_table.add_column("Rule", style="cyan")
    perf_table.add_column("Matches", justify="right", style="green")
    perf_table.add_column("% of Messages", justify="right")

    sorted_rules = sorted(rule_matches.items(), key=lambda kv: len(kv[1]), reverse=True)
    for idx, (name, matched_msgs) in enumerate(sorted_rules, 1):
        count = len(matched_msgs)
        pct = (count / total * 100) if total else 0
        pct_style = "green" if pct >= 10 else ("yellow" if pct >= 1 else "dim")
        perf_table.add_row(
            str(idx),
            name,
            str(count),
            f"[{pct_style}]{pct:.1f}%[/{pct_style}]",
        )

    console.print()
    console.print(perf_table)

    # --- Unmatched messages ---
    unmatched = [m for m in messages if m.get("ID", "") not in matched_ids]

    if unmatched:
        # Group by domain, count senders
        domain_senders: dict[str, Counter] = defaultdict(Counter)
        for msg in unmatched:
            addr = _extract_sender(msg)
            domain = _extract_domain(addr)
            domain_senders[domain][addr] += 1

        # Flatten to (domain, sender, count) and sort by count descending
        rows: list[tuple[str, str, int]] = []
        for domain, counter in domain_senders.items():
            for addr, cnt in counter.items():
                rows.append((domain, addr, cnt))
        rows.sort(key=lambda r: r[2], reverse=True)

        unmatched_table = Table(
            title="Unmatched Senders (candidates for new rules)",
            show_lines=False,
            expand=True,
        )
        unmatched_table.add_column("#", style="dim", width=4)
        unmatched_table.add_column("Domain", style="yellow")
        unmatched_table.add_column("Sender", style="cyan")
        unmatched_table.add_column("Messages", justify="right", style="red")

        display_limit = 25
        for idx, (domain, addr, cnt) in enumerate(rows[:display_limit], 1):
            unmatched_table.add_row(str(idx), domain, addr, str(cnt))

        if len(rows) > display_limit:
            unmatched_table.add_row(
                "", "", f"[dim]...and {len(rows) - display_limit} more[/dim]", ""
            )

        console.print()
        console.print(unmatched_table)

    # --- Summary panel ---
    matched_count = len(matched_ids)
    unmatched_count = total - matched_count
    coverage = (matched_count / total * 100) if total else 0

    coverage_color = "green" if coverage >= 80 else ("yellow" if coverage >= 50 else "red")
    summary_lines = [
        f"[cyan]Messages scanned:[/cyan]  {total}",
        f"[cyan]Matched by rules:[/cyan] {matched_count}",
        f"[cyan]Unmatched:[/cyan]         {unmatched_count}",
        f"[cyan]Coverage:[/cyan]           [{coverage_color}]{coverage:.1f}%[/{coverage_color}]",
    ]

    console.print()
    console.print(
        Panel(
            "\n".join(summary_lines),
            title="Rule Coverage Summary",
            border_style="blue",
        )
    )

    if coverage < 50:
        print_warning(
            "Less than half of your inbox is covered by rules. "
            "Run 'pmo rules suggest' to get suggestions for new rules."
        )
    elif coverage >= 90:
        print_success("Excellent rule coverage!")


# ---------------------------------------------------------------------------
# suggest_rules
# ---------------------------------------------------------------------------


def suggest_rules(
    client: ProtonMailExt,
    rules_file: Optional[str] = None,
    limit: int = 200,
) -> None:
    """Analyse unmatched messages and print suggested YAML rule snippets.

    Suggestions:
    - ``sender_domain`` rule for domains with >= 3 unmatched messages
    - ``sender_is`` rule for specific senders with >= 2 unmatched messages
    """
    rules = load_rules(rules_file)
    if not rules:
        return

    print_info(f"Fetching up to {limit} inbox messages...")
    messages = _fetch_inbox_messages(client, limit=limit)
    if not messages:
        print_warning("No messages in inbox.")
        return

    print_info(f"Evaluating {len(rules)} rule(s) against {len(messages)} message(s)...")

    # Find messages that match NO rules
    unmatched: list[dict] = []
    for msg in messages:
        if not any(matches_conditions(msg, rule.get("conditions", {})) for rule in rules):
            unmatched.append(msg)

    if not unmatched:
        print_success("Every message matched at least one rule. Nothing to suggest!")
        return

    print_info(f"{len(unmatched)} message(s) matched no rules. Analysing...")

    # Group by domain and by sender
    domain_counts: Counter = Counter()
    sender_counts: Counter = Counter()

    for msg in unmatched:
        addr = _extract_sender(msg)
        domain = _extract_domain(addr)
        if addr:
            sender_counts[addr] += 1
        if domain:
            domain_counts[domain] += 1

    # Collect senders already covered by a domain suggestion so we don't
    # duplicate them as sender_is suggestions.
    suggested_domains: set[str] = set()
    snippets: list[str] = []

    # Domain suggestions (>= 3 messages)
    domain_threshold = 3
    for domain, count in domain_counts.most_common():
        if count < domain_threshold:
            break
        suggested_domains.add(domain)
        safe_name = domain.replace(".", "_")
        snippet = (
            f'  - name: "Handle {domain}"\n'
            f"    conditions:\n"
            f'      sender_domain: "{domain}"\n'
            f"    actions:\n"
            f'      add_label: "{safe_name}"  # adjust action as needed\n'
            f"      mark_read: true"
        )
        snippets.append(snippet)

    # Sender suggestions (>= 2 messages, not already covered by domain)
    sender_threshold = 2
    for addr, count in sender_counts.most_common():
        if count < sender_threshold:
            break
        domain = _extract_domain(addr)
        if domain in suggested_domains:
            continue  # already covered by a domain rule
        snippet = (
            f'  - name: "Handle {addr}"\n'
            f"    conditions:\n"
            f'      sender_is: "{addr}"\n'
            f"    actions:\n"
            f'      add_label: "TODO"  # adjust action as needed\n'
            f"      mark_read: true"
        )
        snippets.append(snippet)

    if not snippets:
        print_info(
            "No single sender or domain appears often enough to suggest a rule. "
            "Try increasing --limit to scan more messages."
        )
        return

    # Display as a nice panel with copyable YAML
    console.print()
    console.print(
        Panel(
            f"[bold]Add these to your rules file:[/bold]\n\n[dim]{RULES_FILE}[/dim]\n",
            title="Suggested Rules",
            border_style="green",
        )
    )

    yaml_block = "rules:\n" + "\n\n".join(snippets) + "\n"
    console.print("[green]```yaml[/green]")
    console.print(yaml_block)
    console.print("[green]```[/green]")

    # Summary table
    summary_table = Table(title="Suggestion Summary", show_lines=False)
    summary_table.add_column("Type", style="cyan")
    summary_table.add_column("Count", justify="right", style="green")

    domain_count = len(suggested_domains)
    sender_only_count = len(snippets) - domain_count
    summary_table.add_row("Domain rules (sender_domain)", str(domain_count))
    summary_table.add_row("Sender rules (sender_is)", str(sender_only_count))
    summary_table.add_row("[bold]Total suggestions[/bold]", f"[bold]{len(snippets)}[/bold]")

    console.print()
    console.print(summary_table)

    print_info(
        "\nCopy the YAML above into your rules file and adjust the actions "
        "(add_label, archive, mark_read, etc.) to taste."
    )
