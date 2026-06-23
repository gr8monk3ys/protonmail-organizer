# ProtonMail Organizer

A command-line tool to organize your ProtonMail inbox: search and bulk-manage
messages, auto-sort with a YAML rule engine, compile rules to server-side Sieve
filters, detect newsletters, draft AI replies in your own writing style, and more.

> **Note**: This is an unofficial tool built on the community
> [`protonmail-api-client`](https://pypi.org/project/protonmail-api-client/).
> It is not affiliated with or endorsed by Proton AG. Use at your own risk, and
> always preview destructive operations with `--dry-run` first.

## Features

- **Messages** — list, search (by sender/recipient/keyword/date/attachments), read, and count.
- **Labels & folders** — list, create, delete, and apply, with free-plan limit guards.
- **Cleanup** — bulk-delete old mail, archive by sender, detect newsletters, empty Trash/Spam, and surface unsubscribe links.
- **Rule engine** — declarative YAML rules (`conditions` → `actions`) run on demand or continuously in `watch` mode.
- **Server-side filters** — compile your YAML rules to ProtonMail-compatible Sieve and push them to your account.
- **AI replies** — draft replies with Claude that match your personal writing style (analyzed from your sent mail).
- **Templates** — reusable reply templates with `{sender_first}`, `{subject}`, and other placeholders.
- **Insights** — account stats, top senders, a daily digest of who's waiting on you, and rule-coverage analytics.

## Install

Requires Python 3.9+.

```bash
git clone https://github.com/gr8monk3ys/protonmail-organizer.git
cd protonmail-organizer
pip install -e .

# Optional: AI draft replies (pulls in the anthropic SDK)
pip install -e ".[ai]"
```

This installs the `pmo` command.

## Quick start

```bash
# Log in (session is cached at ~/.config/protonmail-organizer/session.dat, mode 0600)
pmo auth login

# See what's in your inbox
pmo messages list

# Account overview + top senders
pmo stats

# Create starter rules, preview them, then apply
pmo rules init
pmo rules run --dry-run
pmo rules run
```

## Command tour

Run `pmo --help` or `pmo <group> --help` for full details.

### Auth
```bash
pmo auth login      # authenticate (prompts for email, password, 2FA)
pmo auth status     # show the currently authenticated account
pmo auth logout     # remove the saved session
```

### Messages
```bash
pmo messages list --folder 0 --limit 20
pmo messages search --from alice@example.com --days 7
pmo messages search -k "invoice" --has-attachments
pmo messages read <message_id>
pmo messages count
```

### Labels
```bash
pmo labels list --type all
pmo labels create --name "Work" --color "#7272a7"
pmo labels create --name "Receipts" --folder
pmo labels apply <label_id> --messages <id1> --messages <id2>
pmo labels delete <label_id>
```

### Cleanup
```bash
pmo cleanup old --days 90 --dry-run        # delete mail older than 90 days
pmo cleanup sender --pattern "marketing@"  # archive everything from a sender
pmo cleanup newsletters                    # detect newsletters (add --delete to remove)
pmo cleanup empty-trash --spam             # empty Trash (and Spam)
pmo cleanup unsubscribe                     # list one-click unsubscribe links
```

### Rules
```bash
pmo rules init               # write an example rules file
pmo rules list               # show configured rules
pmo rules validate           # check syntax + label references
pmo rules run --dry-run      # preview matches without applying
pmo rules run                # apply actions
pmo rules stats              # rule coverage over your inbox
pmo rules suggest            # suggest new rules for unmatched senders
```

### Server-side filters (Sieve)
```bash
pmo filters preview          # compile your YAML rules to Sieve (no push)
pmo filters push             # compile and upload as a server-side filter
pmo filters list             # show active server-side filters
pmo filters pull             # download and print existing Sieve scripts
pmo filters delete <id>      # remove a filter (or --all)
```

### AI replies & templates
```bash
pmo respond profile --refresh    # analyze your sent mail to learn your style
pmo respond to <message_id>      # draft a reply (review → send/edit/regenerate)
pmo respond interactive          # pick a message from the inbox, then draft

pmo templates create thanks
pmo templates list
pmo templates use thanks <message_id>
```

AI features require an Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Watch, digest & organize
```bash
pmo watch --interval 60      # poll the inbox and auto-apply rules continuously
pmo digest --days 1          # summary of recent activity + who's waiting on you
pmo organize                 # interactive menu-driven mode
```

## Rules format

Rules live at `~/.config/protonmail-organizer/rules.yaml` (or pass `--file`).
Each rule is a set of `conditions` (all must match — AND logic) and `actions`.

```yaml
rules:
  - name: "Label GitHub notifications"
    conditions:
      sender_domain: "github.com"
    actions:
      add_label: "GitHub"
      mark_read: true

  - name: "Delete old unread newsletters"
    conditions:
      sender_contains: "newsletter"
      older_than_days: 60
      unread: true
    actions:
      delete: true
```

**Conditions:** `sender_is`, `sender_contains`, `sender_domain`, `subject_contains`,
`has_attachment`, `older_than_days`, `unread`.

**Actions:** `move_to`, `add_label`, `remove_label`, `mark_read`, `delete`, `archive`, `star`.

Time-based conditions like `older_than_days` only work with `pmo rules run` /
`pmo watch` (they can't be expressed in Sieve), so `pmo filters push` will skip
or partially compile those rules and tell you which.

## Configuration & privacy

- All state lives under `~/.config/protonmail-organizer/` (override with `PMO_CONFIG_DIR`).
- The session file and style profile are written with `0600` permissions.
- The writing-style profile stores only **truncated** snippets (first ~3 sentences,
  capped at 200 chars) of your sent mail. These snippets are sent to the Claude API
  when drafting replies. Delete `style_profile.json` to remove them.

## Development

```bash
pip install -e ".[test]"
pytest                 # run the test suite
ruff check .           # lint
ruff format .          # format
pre-commit install     # enable hooks (ruff, ruff-format, hygiene checks)
```

## License

MIT — see [LICENSE](LICENSE).
