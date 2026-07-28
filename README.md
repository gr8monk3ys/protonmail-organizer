# ProtonMail Organizer

A Python CLI tool for organizing your ProtonMail inbox from the terminal. Manage messages, labels, folders, and cleanup operations with rich terminal output. Define YAML-based rules to auto-organize incoming mail, compile them to server-side Sieve filters, and optionally generate AI-powered draft replies using Claude.

## Features

- **Inbox Management** -- List, search, read, and count messages across all folders with paginated output
- **Label and Folder CRUD** -- Create, list, delete, and apply labels/folders with free-plan limit guards (3 labels, 3 folders)
- **Bulk Cleanup** -- Delete old messages, archive by sender, detect and remove newsletters, empty trash/spam, find unsubscribe links
- **YAML Rule Engine** -- Define rules with sender/subject/age/attachment conditions and archive/label/delete/star actions; run them against your inbox with dry-run support
- **Rule Analytics** -- Measure rule coverage across your inbox, identify unmatched senders, and auto-suggest new rules
- **Server-Side Sieve Filters** -- Compile YAML rules to ProtonMail-compatible Sieve scripts; push, pull, update, and delete filters via the API
- **AI Draft Replies** -- Generate context-aware reply drafts using Claude (Anthropic API) that match your personal writing style
- **Writing Style Profiling** -- Analyze your sent emails to build a style profile (formality, greetings, sign-offs, common phrases) used for AI reply generation
- **Email Templates** -- Create, edit, and apply reusable reply templates with placeholder variables (`{sender_first}`, `{sender_name}`, `{sender_email}`, `{subject}`)
- **Watch Mode** -- Continuously poll your inbox and auto-apply rules to new messages
- **Digest Reports** -- Summarize recent email activity with sender domain breakdown and action items
- **Interactive Mode** -- Menu-driven interface for all operations without memorizing CLI commands
- **Rich Terminal UI** -- Colored tables, progress bars, spinners, and panels via Rich

## Tech Stack

- **Python** >= 3.9
- **[protonmail-api-client](https://pypi.org/project/protonmail-api-client/)** -- Unofficial ProtonMail API client for authentication, message operations, and encryption
- **[Click](https://click.palletsprojects.com/)** -- CLI framework with command groups, options, and arguments
- **[Rich](https://rich.readthedocs.io/)** -- Terminal formatting (tables, panels, progress bars, syntax highlighting)
- **[PyYAML](https://pyyaml.org/)** -- YAML rule file parsing
- **[Anthropic](https://docs.anthropic.com/en/docs/client-sdks/python)** (optional) -- Claude API for AI draft reply generation

## Getting Started

### Prerequisites

- Python 3.9 or later
- A ProtonMail account (free plan supported; paid plan needed for the server-side filter push API)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

Clone the repository and install:

```bash
git clone https://github.com/gr8monk3ys/protonmail-organizer.git
cd protonmail-organizer
```

**With uv (recommended):**

```bash
uv pip install -e .
```

**With pip:**

```bash
pip install -e .
```

**With AI reply support (optional):**

```bash
uv pip install -e ".[ai]"
# or
pip install -e ".[ai]"
```

**With test dependencies:**

```bash
uv pip install -e ".[test]"
# or
pip install -e ".[test]"
```

After installation the `pmo` command is available globally.

## Configuration

Configuration files are stored in `~/.config/protonmail-organizer/` (override with the `PMO_CONFIG_DIR` environment variable).

| File | Purpose |
|------|---------|
| `session.dat` | Encrypted session token (permissions: `0600`) |
| `rules.yaml` | YAML rule definitions |
| `style_profile.json` | Writing style profile for AI replies (permissions: `0600`) |
| `templates.json` | Saved email reply templates (permissions: `0600`) |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PMO_CONFIG_DIR` | No | Override the default config directory |
| `ANTHROPIC_API_KEY` | Only for AI replies | Anthropic API key for Claude (`sk-ant-...`) |
| `EDITOR` | No | Preferred text editor for template editing and draft review |

### Authentication

Log in with your ProtonMail credentials (supports 2FA):

```bash
pmo auth login
```

The session is saved locally with restrictive file permissions. Check session status or log out:

```bash
pmo auth status
pmo auth logout
```

## Usage

### Messages

```bash
# List inbox (default 20 messages)
pmo messages list

# List messages in a specific folder with pagination
pmo messages list --folder 3 --limit 50 --page 1

# Search by keyword, sender, recipient, date range, or attachments
pmo messages search -k "invoice" --from "billing@example.com" --days 30

# Read a specific message
pmo messages read <message-id>

# Show message counts by folder
pmo messages count
```

### Labels and Folders

```bash
# List all labels, folders, and system labels
pmo labels list
pmo labels list --type labels
pmo labels list --type folders

# Create a label or folder
pmo labels create --name "Receipts"
pmo labels create --name "Work" --folder --color "#69a9d1"

# Delete a label
pmo labels delete <label-id>
pmo labels delete <label-id> -y   # skip confirmation

# Apply or remove a label from messages
pmo labels apply <label-id> --messages <msg-id-1> --messages <msg-id-2>
pmo labels apply <label-id> --messages <msg-id> --remove
```

### Cleanup

```bash
# Delete messages older than 90 days from inbox
pmo cleanup old --days 90
pmo cleanup old --days 90 --dry-run   # preview first

# Archive all messages from a sender pattern
pmo cleanup sender --pattern "noreply@example.com"

# Detect newsletters in your inbox
pmo cleanup newsletters
pmo cleanup newsletters --delete

# Empty trash (and optionally spam)
pmo cleanup empty-trash
pmo cleanup empty-trash --spam -y

# Find messages with unsubscribe links
pmo cleanup unsubscribe --limit 100
```

### Rules

Rules are defined in YAML. Initialize an example rules file:

```bash
pmo rules init
```

This creates `~/.config/protonmail-organizer/rules.yaml`. Example:

```yaml
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
```

**Available conditions:** `sender_is`, `sender_contains`, `sender_domain`, `subject_contains`, `has_attachment`, `older_than_days`, `unread`

**Available actions:** `move_to`, `add_label`, `remove_label`, `mark_read`, `delete`, `archive`, `star`

```bash
# List configured rules
pmo rules list

# Validate rules (checks syntax and label references)
pmo rules validate

# Run rules against inbox (with dry-run preview)
pmo rules run --dry-run
pmo rules run

# Use a custom rules file
pmo rules run --file /path/to/custom-rules.yaml

# View rule coverage statistics
pmo rules stats --limit 500

# Get suggestions for new rules based on unmatched messages
pmo rules suggest
```

### Server-Side Sieve Filters

Compile your YAML rules to ProtonMail-compatible Sieve scripts:

```bash
# Preview compiled Sieve without pushing
pmo filters preview

# Push rules as a server-side filter
pmo filters push

# List active server-side filters
pmo filters list

# Download and display filter Sieve code
pmo filters pull

# Update an existing filter
pmo filters update <filter-id>

# Delete a filter
pmo filters delete <filter-id>
pmo filters delete --all
```

> **Note:** The filter push API may require a paid ProtonMail plan. If the API is not accessible, use `pmo filters preview` and paste the Sieve code manually in ProtonMail Settings > Filters > Add Sieve filter.

### AI Draft Replies

Generate reply drafts that match your writing style using Claude:

```bash
# Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Generate a reply for a specific message
pmo respond to <message-id>
pmo respond to <message-id> --context "Decline politely, suggest next week"

# Interactive mode: pick a message and draft a reply
pmo respond interactive

# View or rebuild your writing style profile
pmo respond profile
pmo respond profile --refresh --samples 100
```

The draft review flow lets you **send**, **edit** (opens `$EDITOR`), **regenerate** with new instructions, or **cancel**.

### Templates

```bash
# List all templates
pmo templates list

# Create a template (opens $EDITOR if no --body provided)
pmo templates create meeting-followup
pmo templates create quick-ack --body "Hi {sender_first}, got it. Thanks!"

# Show, edit, or delete a template
pmo templates show meeting-followup
pmo templates edit meeting-followup
pmo templates delete meeting-followup

# Apply a template as a reply to a message
pmo templates use quick-ack <message-id>
```

**Supported placeholders:** `{sender_first}`, `{sender_name}`, `{sender_email}`, `{subject}`

### Watch Mode

Continuously poll your inbox and auto-apply rules to new messages:

```bash
# Watch with default 60-second interval
pmo watch

# Custom interval
pmo watch --interval 120

# Use a specific rules file
pmo watch --file /path/to/rules.yaml
```

Press `Ctrl+C` to stop. A summary of actions taken during the session is displayed on exit.

### Other Commands

```bash
# Digest report of recent email activity
pmo digest
pmo digest --days 7

# Account stats (message counts, top senders, label usage)
pmo stats

# Interactive menu-driven mode
pmo organize
```

## Project Structure

```
protonmail-organizer/
├── src/
│   └── protonmail_organizer/
│       ├── __init__.py          # Package version
│       ├── __main__.py          # python -m entry point
│       ├── cli.py               # Click CLI command definitions
│       ├── auth.py              # Login, logout, session management
│       ├── client_ext.py        # Extended ProtonMail API client
│       ├── config.py            # Config directory and file paths
│       ├── constants.py         # System labels, colors, limits
│       ├── display.py           # Rich terminal output helpers
│       ├── messages.py          # Message listing, search, stats, digest
│       ├── labels.py            # Label/folder CRUD with plan guards
│       ├── cleanup.py           # Bulk delete, archive, newsletter detection
│       ├── rules.py             # YAML rule engine
│       ├── rule_analytics.py    # Rule coverage stats and suggestions
│       ├── filters.py           # Sieve compiler and server-side filter CRUD
│       ├── responder.py         # AI draft reply generator (Claude)
│       ├── style_profile.py     # Sent email analyzer for writing style
│       ├── templates.py         # Reusable email reply templates
│       ├── interactive.py       # Interactive menu-driven mode
│       └── watch.py             # Polling watch mode
├── tests/
│   ├── conftest.py              # Shared test fixtures
│   ├── test_cli.py
│   ├── test_cleanup.py
│   ├── test_filters.py
│   ├── test_rules.py
│   └── test_style_profile.py
├── rules/
│   └── example_rules.yaml       # Example YAML rules file
├── pyproject.toml               # Build config and dependencies
├── uv.lock                      # Lockfile
└── LICENSE                      # MIT License
```

## Running Tests

```bash
# Install test dependencies
pip install -e ".[test]"

# Run tests
pytest
```

## License

MIT. See [LICENSE](LICENSE) for details.
