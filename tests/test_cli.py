"""Basic CLI smoke tests using Click's CliRunner.

These tests verify that help text renders and exits cleanly for all
top-level commands and subcommand groups, without requiring a real
ProtonMail connection.
"""

from __future__ import annotations

from click.testing import CliRunner

from protonmail_organizer.cli import cli

runner = CliRunner()


class TestCLIHelp:
    """Smoke tests: every command's --help exits 0 and contains useful text."""

    def test_cli_help(self):
        """pmo --help exits 0 and shows description."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "ProtonMail Organizer" in result.output

    def test_cli_version(self):
        """pmo --version exits 0 and prints a version string."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        # The version string should contain the package version
        assert "version" in result.output.lower() or "0." in result.output

    def test_auth_help(self):
        """pmo auth --help exits 0 and mentions login."""
        result = runner.invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "auth" in result.output.lower() or "Login" in result.output

    def test_messages_help(self):
        """pmo messages --help exits 0 and mentions list/search."""
        result = runner.invoke(cli, ["messages", "--help"])
        assert result.exit_code == 0
        assert "messages" in result.output.lower() or "list" in result.output.lower()

    def test_filters_help(self):
        """pmo filters --help exits 0 and mentions Sieve."""
        result = runner.invoke(cli, ["filters", "--help"])
        assert result.exit_code == 0
        assert "filter" in result.output.lower() or "Sieve" in result.output

    def test_rules_help(self):
        """pmo rules --help exits 0 and mentions YAML/rule."""
        result = runner.invoke(cli, ["rules", "--help"])
        assert result.exit_code == 0
        assert "rule" in result.output.lower()

    def test_cleanup_help(self):
        """pmo cleanup --help exits 0 and mentions delete/archive."""
        result = runner.invoke(cli, ["cleanup", "--help"])
        assert result.exit_code == 0
        assert "cleanup" in result.output.lower() or "delete" in result.output.lower()

    def test_respond_help(self):
        """pmo respond --help exits 0 and mentions AI/draft."""
        result = runner.invoke(cli, ["respond", "--help"])
        assert result.exit_code == 0
        assert "respond" in result.output.lower() or "draft" in result.output.lower()


class TestSubcommandHelp:
    """Smoke tests for deeper subcommands that should also show help cleanly."""

    def test_auth_login_help(self):
        """pmo auth login --help exits 0."""
        result = runner.invoke(cli, ["auth", "login", "--help"])
        assert result.exit_code == 0

    def test_messages_list_help(self):
        """pmo messages list --help exits 0."""
        result = runner.invoke(cli, ["messages", "list", "--help"])
        assert result.exit_code == 0

    def test_rules_init_help(self):
        """pmo rules init --help exits 0."""
        result = runner.invoke(cli, ["rules", "init", "--help"])
        assert result.exit_code == 0

    def test_filters_preview_help(self):
        """pmo filters preview --help exits 0."""
        result = runner.invoke(cli, ["filters", "preview", "--help"])
        assert result.exit_code == 0

    def test_cleanup_old_help(self):
        """pmo cleanup old --help exits 0."""
        result = runner.invoke(cli, ["cleanup", "old", "--help"])
        assert result.exit_code == 0

    def test_cleanup_newsletters_help(self):
        """pmo cleanup newsletters --help exits 0."""
        result = runner.invoke(cli, ["cleanup", "newsletters", "--help"])
        assert result.exit_code == 0

    def test_respond_profile_help(self):
        """pmo respond profile --help exits 0."""
        result = runner.invoke(cli, ["respond", "profile", "--help"])
        assert result.exit_code == 0
