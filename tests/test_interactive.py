"""Tests for the table-driven interactive menu."""

from __future__ import annotations

from protonmail_organizer import interactive


class TestMenuTable:
    def test_menu_text_lists_every_item_with_its_number(self):
        """The rendered menu is derived from MENU_ITEMS — it cannot drift."""
        menu = interactive._render_menu()
        for i, (label, _handler) in enumerate(interactive.MENU_ITEMS, 1):
            assert f"[{i}] {label}" in menu
        assert "\\[q] Quit" in menu  # escaped so Rich renders the brackets

    def test_labels_are_unique(self):
        labels = [label for label, _ in interactive.MENU_ITEMS]
        assert len(labels) == len(set(labels))

    def test_menu_covers_undo_and_filter_push(self):
        """The two operations the old hand-written menu drifted away from."""
        labels = " | ".join(label.lower() for label, _ in interactive.MENU_ITEMS)
        assert "undo" in labels
        assert "push" in labels


class TestDispatch:
    def test_choice_dispatches_to_matching_handler(self, mock_client, monkeypatch):
        calls = []
        monkeypatch.setattr(
            interactive,
            "MENU_ITEMS",
            [
                ("First", lambda c: calls.append(("first", c))),
                ("Second", lambda c: calls.append(("second", c))),
            ],
        )
        interactive._handle_choice(mock_client, "2")
        assert calls == [("second", mock_client)]

    def test_out_of_range_choice_warns_without_crashing(self, mock_client, capsys):
        interactive._handle_choice(mock_client, "99")
        assert "unknown option" in capsys.readouterr().out.lower()

    def test_non_numeric_choice_warns_without_crashing(self, mock_client, capsys):
        interactive._handle_choice(mock_client, "banana")
        assert "unknown option" in capsys.readouterr().out.lower()


class TestNewsletterHandlerConsistency:
    def test_newsletter_handler_prompts_instead_of_hardcoding_dry_run(
        self, mock_client, monkeypatch
    ):
        """The old menu hard-coded dry_run=True while sibling items prompted."""
        answers = iter(["y", "n"])  # delete them? -> yes; dry run? -> no
        monkeypatch.setattr(interactive.console, "input", lambda *a, **k: next(answers))
        captured = {}

        def fake_handle_newsletters(client, dry_run=False, do_delete=False, **kw):
            captured.update(dry_run=dry_run, do_delete=do_delete)

        import protonmail_organizer.cleanup as cleanup

        monkeypatch.setattr(cleanup, "handle_newsletters", fake_handle_newsletters)
        interactive._newsletters(mock_client)
        assert captured == {"dry_run": False, "do_delete": True}
