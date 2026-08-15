"""Contract tests for ProtonMailExt request building and response parsing.

This is the riskiest surface in the project: hand-built calls to ProtonMail's
private, undocumented web API. These tests mock the HTTP verb methods
(`_get`/`_post`/`_put`/`_delete`) and assert that each client method targets the
right endpoint, sends the right payload/params, and parses the response
correctly. If an endpoint or payload shape drifts, these fail loudly — unlike
the higher-level tests that run against a fully stubbed client.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from protonmail_organizer.client_ext import BASE, ProtonMailExt


def make_client() -> ProtonMailExt:
    """Build a ProtonMailExt without running the real constructor."""
    client = ProtonMailExt.__new__(ProtonMailExt)
    client._get = MagicMock()
    client._post = MagicMock()
    client._put = MagicMock()
    client._delete = MagicMock()
    return client


class TestLabelCRUD:
    def test_create_label_minimal_payload(self):
        c = make_client()
        c._post.return_value.json.return_value = {"Label": {"ID": "L1", "Name": "Work"}}
        out = c.create_label("Work", "#7272a7")
        c._post.assert_called_once_with(
            BASE, "core/v4/labels", json={"Name": "Work", "Color": "#7272a7", "Type": 1}
        )
        assert out == {"ID": "L1", "Name": "Work"}

    def test_create_label_includes_parent_and_type(self):
        c = make_client()
        c._post.return_value.json.return_value = {"Label": {}}
        c.create_label("Sub", "#fff", label_type=3, parent_id="P1")
        payload = c._post.call_args.kwargs["json"]
        assert payload["Type"] == 3
        assert payload["ParentID"] == "P1"

    def test_create_label_missing_key_returns_empty(self):
        c = make_client()
        c._post.return_value.json.return_value = {}
        assert c.create_label("X", "#fff") == {}

    def test_delete_label_targets_id(self):
        c = make_client()
        c._delete.return_value.json.return_value = {"Code": 1000}
        out = c.delete_label("L9")
        c._delete.assert_called_once_with(BASE, "core/v4/labels/L9")
        assert out == {"Code": 1000}

    def test_update_label_sends_only_provided_fields(self):
        c = make_client()
        c._put.return_value.json.return_value = {"Label": {"ID": "L1", "Name": "New"}}
        out = c.update_label("L1", name="New")
        c._put.assert_called_once_with(BASE, "core/v4/labels/L1", json={"Name": "New"})
        assert out["Name"] == "New"

    def test_update_label_noop_skips_request(self):
        c = make_client()
        assert c.update_label("L1") == {}
        c._put.assert_not_called()


class TestSearch:
    def test_builds_params_and_parses_messages(self):
        c = make_client()
        c._get.return_value.json.return_value = {"Messages": [{"ID": "m1"}]}
        out = c.search_messages(
            keyword="invoice",
            sender="a@b.com",
            recipient="c@d.com",
            begin=100,
            end=200,
            has_attachments=True,
            label_id="0",
        )
        endpoint = c._get.call_args.args
        assert endpoint == (BASE, "mail/v4/messages")
        params = c._get.call_args.kwargs["params"]
        assert params["Keyword"] == "invoice"
        assert params["From"] == "a@b.com"
        assert params["To"] == "c@d.com"
        assert params["Begin"] == 100
        assert params["End"] == 200
        assert params["Attachments"] == 1
        assert params["LabelID"] == "0"
        assert out == [{"ID": "m1"}]

    def test_has_attachments_false_maps_to_zero(self):
        c = make_client()
        c._get.return_value.json.return_value = {"Messages": []}
        c.search_messages(has_attachments=False)
        assert c._get.call_args.kwargs["params"]["Attachments"] == 0

    def test_omits_unset_filters_keeps_defaults(self):
        c = make_client()
        c._get.return_value.json.return_value = {"Messages": []}
        c.search_messages()
        params = c._get.call_args.kwargs["params"]
        for key in ("Keyword", "From", "To", "Begin", "End", "Attachments", "LabelID"):
            assert key not in params
        assert params["Page"] == 0
        assert params["PageSize"] == 50
        assert params["Sort"] == "Time"
        assert params["Desc"] == 1

    def test_missing_messages_key_returns_empty_list(self):
        c = make_client()
        c._get.return_value.json.return_value = {}
        assert c.search_messages() == []

    def test_search_all_stops_on_short_page(self):
        c = make_client()
        page0 = [{"ID": str(i)} for i in range(50)]
        page1 = [{"ID": "tail"}]
        c.search_messages = MagicMock(side_effect=[page0, page1, []])
        out = c.search_messages_all(page_size=50)
        assert len(out) == 51
        assert c.search_messages.call_count == 2  # stopped after the short page

    def test_search_all_stops_on_empty_page(self):
        c = make_client()
        c.search_messages = MagicMock(side_effect=[[], [{"ID": "never"}]])
        assert c.search_messages_all(page_size=50) == []
        assert c.search_messages.call_count == 1

    def test_search_all_respects_max_pages(self):
        c = make_client()
        full = [{"ID": str(i)} for i in range(50)]
        c.search_messages = MagicMock(return_value=full)
        out = c.search_messages_all(max_pages=3, page_size=50)
        assert c.search_messages.call_count == 3
        assert len(out) == 150


class TestConversationLabels:
    def test_set_label_payload(self):
        c = make_client()
        c._put.return_value.json.return_value = {"Code": 1000}
        c.set_label_for_conversations("LBL", ["c1", "c2"])
        c._put.assert_called_once_with(
            BASE, "mail/v4/conversations/label", json={"LabelID": "LBL", "IDs": ["c1", "c2"]}
        )

    def test_unset_label_targets_unlabel_endpoint(self):
        c = make_client()
        c._put.return_value.json.return_value = {"Code": 1000}
        c.unset_label_for_conversations("LBL", ["c1"])
        assert c._put.call_args.args[1] == "mail/v4/conversations/unlabel"


class TestFilters:
    def test_get_filters_parses_list(self):
        c = make_client()
        c._get.return_value.json.return_value = {"Filters": [{"ID": "f1"}]}
        out = c.get_filters()
        c._get.assert_called_once_with(BASE, "mail/v4/filters")
        assert out == [{"ID": "f1"}]

    def test_create_filter_payload(self):
        c = make_client()
        c._post.return_value.json.return_value = {"Filter": {"ID": "f1"}}
        out = c.create_filter("My filter", "require [];")
        payload = c._post.call_args.kwargs["json"]
        assert c._post.call_args.args == (BASE, "mail/v4/filters")
        assert payload == {"Name": "My filter", "Status": 1, "Version": 2, "Sieve": "require [];"}
        assert out == {"ID": "f1"}

    def test_update_filter_targets_id_and_optional_name(self):
        c = make_client()
        c._put.return_value.json.return_value = {"Filter": {}}
        c.update_filter("f1", "sieve", name="Renamed")
        assert c._put.call_args.args == (BASE, "mail/v4/filters/f1")
        assert c._put.call_args.kwargs["json"]["Name"] == "Renamed"

    def test_delete_filter_targets_id(self):
        c = make_client()
        c._delete.return_value.json.return_value = {"Code": 1000}
        c.delete_filter("f1")
        c._delete.assert_called_once_with(BASE, "mail/v4/filters/f1")


class TestGetMessage:
    def test_get_message_targets_id_and_parses(self):
        c = make_client()
        c._get.return_value.json.return_value = {"Message": {"ID": "m1", "Subject": "Hi"}}
        out = c.get_message("m1")
        c._get.assert_called_once_with(BASE, "mail/v4/messages/m1")
        assert out["Subject"] == "Hi"


class TestSearchTruncationSignal:
    def test_search_all_flags_truncation_at_max_pages(self):
        c = make_client()
        full = [{"ID": str(i)} for i in range(50)]
        c.search_messages = MagicMock(return_value=full)
        out = c.search_messages_all(max_pages=2, page_size=50)
        assert len(out) == 100
        assert out.truncated is True

    def test_search_all_not_truncated_on_short_last_page(self):
        c = make_client()
        full = [{"ID": str(i)} for i in range(50)]
        short = [{"ID": "last"}]
        c.search_messages = MagicMock(side_effect=[full, short])
        out = c.search_messages_all(max_pages=10, page_size=50)
        assert out.truncated is False
