"""Extended ProtonMail client with additional API operations."""

from __future__ import annotations

from typing import Optional

from protonmail import ProtonMail
from protonmail.models import AccountAddress, PgpPairKeys

from .constants import LABEL_TYPE_LABEL

# The library uses 'mail' as the base key for urls_api, with the
# full API path as the endpoint (e.g. 'core/v4/labels', 'mail/v4/messages').
BASE = "mail"


class MessageList(list):
    """Message search results; truncated=True means the page cap cut them off."""

    truncated: bool = False


class ProtonMailExt(ProtonMail):
    """ProtonMail client extended with label CRUD, search, and conversation label ops."""

    def _parse_info_after_login(self, password, user_private_key_password=None):
        """Override to skip undecryptable address keys instead of crashing."""
        user_info = self._ProtonMail__get_users()["User"]
        user_pair_key = user_info["Keys"][0]

        if not user_private_key_password:
            user_private_key_password = self._get_user_private_key_password(password)

        self.pgp.pairs_keys.append(
            PgpPairKeys(
                is_user_key=True,
                is_primary=True,
                fingerprint_private=user_pair_key["Fingerprint"],
                private_key=user_pair_key["PrivateKey"],
                passphrase=user_private_key_password,
                email=user_info["Email"],
            )
        )
        self.logger.info("got user keys", "green")

        account_addresses = self._ProtonMail__addresses()["Addresses"]
        self.account_addresses = [
            AccountAddress(id=aa["ID"], email=aa["Email"], name=aa["DisplayName"])
            for aa in account_addresses
        ]

        for aa in account_addresses:
            for ak in aa["Keys"]:
                try:
                    ap = self.pgp.decrypt(
                        ak["Token"],
                        user_pair_key["PrivateKey"],
                        user_private_key_password,
                    )
                    self.pgp.pairs_keys.append(
                        PgpPairKeys(
                            is_user_key=False,
                            is_primary=bool(ak["Primary"]),
                            fingerprint_public=ak["Fingerprints"][0],
                            fingerprint_private=ak["Fingerprints"][1],
                            public_key=ak["PublicKey"],
                            private_key=ak["PrivateKey"],
                            passphrase=ap,
                            email=aa["Email"],
                        )
                    )
                except Exception:
                    pass  # skip undecryptable address keys (old/unused)
        self.logger.info("got email keys", "green")

    # --- Label CRUD ---

    def create_label(
        self,
        name: str,
        color: str,
        label_type: int = LABEL_TYPE_LABEL,
        parent_id: Optional[str] = None,
    ) -> dict:
        """Create a new label or folder.

        Args:
            name: Label display name.
            color: Hex color string (e.g. "#7272a7").
            label_type: 1 for label, 3 for folder.
            parent_id: Parent folder ID for nested folders (optional).

        Returns:
            The created label data from the API response.
        """
        payload = {
            "Name": name,
            "Color": color,
            "Type": label_type,
        }
        if parent_id is not None:
            payload["ParentID"] = parent_id

        response = self._post(BASE, "core/v4/labels", json=payload)
        return response.json().get("Label", {})

    def delete_label(self, label_id: str) -> dict:
        """Delete a label or folder by ID."""
        response = self._delete(BASE, f"core/v4/labels/{label_id}")
        return response.json()

    def update_label(
        self,
        label_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
    ) -> dict:
        """Update a label's name or color."""
        payload = {}
        if name is not None:
            payload["Name"] = name
        if color is not None:
            payload["Color"] = color
        if not payload:
            return {}

        response = self._put(BASE, f"core/v4/labels/{label_id}", json=payload)
        return response.json().get("Label", {})

    # --- Message Search ---

    def search_messages(
        self,
        keyword: Optional[str] = None,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        begin: Optional[int] = None,
        end: Optional[int] = None,
        has_attachments: Optional[bool] = None,
        label_id: Optional[str] = None,
        page: int = 0,
        page_size: int = 50,
        sort: str = "Time",
        desc: int = 1,
    ) -> list:
        """Search messages with filters via GET /mail/v4/messages.

        Args:
            keyword: Search term in subject/body.
            sender: Filter by sender address.
            recipient: Filter by recipient address.
            begin: Start timestamp (unix epoch).
            end: End timestamp (unix epoch).
            has_attachments: Filter by attachment presence.
            label_id: Filter by label/folder ID.
            page: Page number (0-indexed).
            page_size: Results per page.
            sort: Sort field.
            desc: 1 for descending, 0 for ascending.

        Returns:
            List of message dicts from the API.
        """
        params = {
            "Page": page,
            "PageSize": page_size,
            "Sort": sort,
            "Desc": desc,
        }
        if keyword:
            params["Keyword"] = keyword
        if sender:
            params["From"] = sender
        if recipient:
            params["To"] = recipient
        if begin is not None:
            params["Begin"] = begin
        if end is not None:
            params["End"] = end
        if has_attachments is not None:
            params["Attachments"] = 1 if has_attachments else 0
        if label_id is not None:
            params["LabelID"] = label_id

        response = self._get(BASE, "mail/v4/messages", params=params)
        data = response.json()
        return data.get("Messages", [])

    def search_messages_all(self, max_pages: int = 100, **kwargs) -> "MessageList":
        """Search messages across all pages. Same args as search_messages.

        Args:
            max_pages: Safety limit on number of pages to fetch (default: 100).

        Returns:
            A MessageList; its ``truncated`` attribute is True when the
            max_pages cap stopped the search before results were exhausted,
            meaning more messages match than were returned. Callers doing
            bulk mutations should surface that (see display.warn_if_truncated).
        """
        all_messages = MessageList()
        page = 0
        page_size = kwargs.get("page_size", 50)
        while page < max_pages:
            batch = self.search_messages(page=page, **kwargs)
            if not batch:
                break
            all_messages.extend(batch)
            if len(batch) < page_size:
                break  # last page
            page += 1
        else:
            all_messages.truncated = True
        return all_messages

    # --- Conversation Label Operations ---

    def set_label_for_conversations(self, label_id: str, conversation_ids: list) -> dict:
        """Apply a label to conversations."""
        payload = {
            "LabelID": label_id,
            "IDs": conversation_ids,
        }
        response = self._put(BASE, "mail/v4/conversations/label", json=payload)
        return response.json()

    def unset_label_for_conversations(self, label_id: str, conversation_ids: list) -> dict:
        """Remove a label from conversations."""
        payload = {
            "LabelID": label_id,
            "IDs": conversation_ids,
        }
        response = self._put(BASE, "mail/v4/conversations/unlabel", json=payload)
        return response.json()

    # --- Server-Side Filters (Sieve) ---

    def get_filters(self) -> list:
        """List all server-side mail filters."""
        response = self._get(BASE, "mail/v4/filters")
        return response.json().get("Filters", [])

    def create_filter(self, name: str, sieve_code: str) -> dict:
        """Create a new server-side Sieve filter.

        Args:
            name: Display name for the filter.
            sieve_code: Raw Sieve script code.

        Returns:
            The created filter data from the API.
        """
        payload = {
            "Name": name,
            "Status": 1,  # enabled
            "Version": 2,  # Sieve v2
            "Sieve": sieve_code,
        }
        response = self._post(BASE, "mail/v4/filters", json=payload)
        return response.json().get("Filter", {})

    def update_filter(self, filter_id: str, sieve_code: str, name: Optional[str] = None) -> dict:
        """Update an existing server-side filter.

        Args:
            filter_id: The filter ID to update.
            sieve_code: New Sieve script code.
            name: Optional new display name.

        Returns:
            The updated filter data from the API.
        """
        payload = {
            "Status": 1,
            "Version": 2,
            "Sieve": sieve_code,
        }
        if name is not None:
            payload["Name"] = name
        response = self._put(BASE, f"mail/v4/filters/{filter_id}", json=payload)
        return response.json().get("Filter", {})

    def delete_filter(self, filter_id: str) -> dict:
        """Delete a server-side filter by ID."""
        response = self._delete(BASE, f"mail/v4/filters/{filter_id}")
        return response.json()

    # --- Message Reading (full body) ---

    def get_message(self, message_id: str) -> dict:
        """Get a single message by ID (raw API dict, not decrypted)."""
        response = self._get(BASE, f"mail/v4/messages/{message_id}")
        return response.json().get("Message", {})
