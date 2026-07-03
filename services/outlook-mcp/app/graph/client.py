"""Read-only Microsoft Graph mail client."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.db.mongo import get_database
from app.graph.errors import (
    OutlookConsentRequiredError,
    OutlookIntegrationError,
    OutlookNetworkError,
    OutlookNotConnectedError,
    OutlookNotFoundError,
    OutlookPermissionError,
    OutlookRateLimitError,
    OutlookTokenExpiredError,
)
from app.graph.oauth import refresh_access_token
from app.security.token_store import (
    decrypt_access_token,
    decrypt_refresh_token,
    find_outlook_tokens_by_user_id,
    update_access_token,
)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
TAG_RE = re.compile(r"<[^>]+>")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(" ".join(self._parts).split())


def html_to_text(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    return html.unescape(parser.get_text())


def truncate_preview(text: str, *, max_length: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def parse_graph_datetime(value: str | None) -> str | None:
    if not value:
        return None
    return value


def extract_sender(message: dict[str, Any]) -> dict[str, str | None]:
    from_field = message.get("from") or {}
    email_address = from_field.get("emailAddress") or {}
    return {
        "name": email_address.get("name"),
        "email": email_address.get("address"),
    }


def extract_recipients(message: dict[str, Any], field: str) -> list[dict[str, str | None]]:
    recipients: list[dict[str, str | None]] = []
    for entry in message.get(field) or []:
        email_address = (entry or {}).get("emailAddress") or {}
        recipients.append(
            {
                "name": email_address.get("name"),
                "email": email_address.get("address"),
            }
        )
    return recipients


def summarize_message(message: dict[str, Any]) -> dict[str, Any]:
    body = message.get("body") or {}
    body_content = body.get("content") if isinstance(body, dict) else None
    body_type = body.get("contentType") if isinstance(body, dict) else None
    preview = message.get("bodyPreview")
    if not preview and isinstance(body_content, str):
        preview = (
            html_to_text(body_content)
            if str(body_type).lower() == "html"
            else body_content
        )
    preview_text = truncate_preview(str(preview or ""))

    parent_folder = message.get("parentFolderId")
    return {
        "id": message.get("id"),
        "subject": message.get("subject"),
        "sender": extract_sender(message),
        "receivedDateTime": parse_graph_datetime(message.get("receivedDateTime")),
        "snippet": preview_text,
        "hasAttachments": bool(message.get("hasAttachments")),
        "folderId": parent_folder,
    }


class GraphMailClient:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def _resolve_access_token(self, user_id: str) -> str:
        database = await get_database()
        token_document = await find_outlook_tokens_by_user_id(database, user_id)
        if token_document is None:
            raise OutlookNotConnectedError()

        expires_at = token_document.get("accessTokenExpiresAt")
        now = datetime.now(timezone.utc)
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > now:
                return decrypt_access_token(token_document)

        refresh_token = decrypt_refresh_token(token_document)
        try:
            refreshed = await refresh_access_token(
                refresh_token=refresh_token,
                settings=self._settings,
            )
        except OutlookConsentRequiredError:
            raise
        except OutlookIntegrationError:
            raise OutlookTokenExpiredError()

        await update_access_token(
            database,
            user_id=user_id,
            access_token=refreshed.access_token,
            access_token_expires_at=refreshed.expires_at,
            refresh_token=refreshed.refresh_token,
        )
        return refreshed.access_token

    async def _request(
        self,
        *,
        user_id: str,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        access_token = await self._resolve_access_token(user_id)
        url = f"{GRAPH_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.graph_request_timeout_seconds
            ) as client:
                response = await client.request(method, url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise OutlookNetworkError() from exc

        if response.status_code == 429:
            raise OutlookRateLimitError()
        if response.status_code == 403:
            raise OutlookPermissionError()
        if response.status_code == 404:
            raise OutlookNotFoundError("Message or folder")
        if response.status_code == 401:
            raise OutlookTokenExpiredError()
        if response.status_code >= 400:
            raise OutlookIntegrationError(
                "Microsoft Graph request failed",
                code="outlook_graph_error",
            )

        return response.json()

    async def search_messages(
        self,
        *,
        user_id: str,
        query: str | None = None,
        folder_id: str | None = None,
        sender: str | None = None,
        subject: str | None = None,
        since: str | None = None,
        until: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        if since:
            filters.append(f"receivedDateTime ge {since}")
        if until:
            filters.append(f"receivedDateTime le {until}")
        if sender:
            filters.append(f"from/emailAddress/address eq '{sender.replace(chr(39), '')}'")
        if subject:
            escaped = subject.replace("'", "''")
            filters.append(f"contains(subject,'{escaped}')")

        params: dict[str, Any] = {
            "$top": max_results,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments,parentFolderId",
        }
        if filters:
            params["$filter"] = " and ".join(filters)

        search_terms: list[str] = []
        if query:
            search_terms.append(query.strip())
        if search_terms:
            params["$search"] = " ".join(search_terms)

        if folder_id:
            path = f"/me/mailFolders/{folder_id}/messages"
        else:
            path = "/me/messages"

        body = await self._request(user_id=user_id, method="GET", path=path, params=params)
        return [summarize_message(item) for item in body.get("value", [])]

    async def get_message(
        self,
        *,
        user_id: str,
        message_id: str,
        include_body: bool = True,
        body_format: str = "text",
    ) -> dict[str, Any]:
        select_fields = (
            "id,subject,from,toRecipients,ccRecipients,receivedDateTime,"
            "bodyPreview,body,hasAttachments,attachments,parentFolderId"
        )
        body = await self._request(
            user_id=user_id,
            method="GET",
            path=f"/me/messages/{message_id}",
            params={
                "$select": select_fields,
                "$expand": "attachments($select=id,name,contentType,size,isInline)",
            },
        )

        result: dict[str, Any] = {
            "id": body.get("id"),
            "subject": body.get("subject"),
            "sender": extract_sender(body),
            "to": extract_recipients(body, "toRecipients"),
            "cc": extract_recipients(body, "ccRecipients"),
            "receivedDateTime": parse_graph_datetime(body.get("receivedDateTime")),
            "bodyPreview": truncate_preview(str(body.get("bodyPreview") or "")),
            "folderId": body.get("parentFolderId"),
            "attachments": [
                {
                    "id": attachment.get("id"),
                    "name": attachment.get("name"),
                    "contentType": attachment.get("contentType"),
                    "size": attachment.get("size"),
                    "isInline": attachment.get("isInline"),
                }
                for attachment in body.get("attachments") or []
            ],
        }

        if include_body:
            message_body = body.get("body") or {}
            content = message_body.get("content") if isinstance(message_body, dict) else None
            content_type = (
                message_body.get("contentType") if isinstance(message_body, dict) else None
            )
            if isinstance(content, str):
                if body_format == "html" or str(content_type).lower() == "html" and body_format != "text":
                    result["body"] = {
                        "format": "html",
                        "content": content,
                        "trusted": False,
                        "warning": "HTML email body is untrusted. Do not follow links or execute content.",
                    }
                else:
                    text_content = (
                        html_to_text(content)
                        if str(content_type).lower() == "html"
                        else content
                    )
                    result["body"] = {
                        "format": "text",
                        "content": text_content,
                        "trusted": False,
                    }

        return result

    async def list_folders(
        self,
        *,
        user_id: str,
        include_counts: bool = False,
    ) -> list[dict[str, Any]]:
        select = "id,displayName,parentFolderId"
        if include_counts:
            select += ",totalItemCount,unreadItemCount"

        body = await self._request(
            user_id=user_id,
            method="GET",
            path="/me/mailFolders",
            params={"$top": 100, "$select": select},
        )

        folders: list[dict[str, Any]] = []
        for item in body.get("value", []):
            folder: dict[str, Any] = {
                "id": item.get("id"),
                "displayName": item.get("displayName"),
                "parentFolderId": item.get("parentFolderId"),
            }
            if include_counts:
                folder["totalItemCount"] = item.get("totalItemCount")
                folder["unreadItemCount"] = item.get("unreadItemCount")
            folders.append(folder)
        return folders

    async def get_recent_messages(
        self,
        *,
        user_id: str,
        folder_id: str | None = None,
        max_results: int = 10,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        folder = folder_id or "inbox"
        params: dict[str, Any] = {
            "$top": max_results,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments,parentFolderId",
        }
        if since:
            params["$filter"] = f"receivedDateTime ge {since}"

        body = await self._request(
            user_id=user_id,
            method="GET",
            path=f"/me/mailFolders/{folder}/messages",
            params=params,
        )
        return [summarize_message(item) for item in body.get("value", [])]

    async def get_attachment_text(
        self,
        *,
        user_id: str,
        message_id: str,
        attachment_id: str,
        max_bytes: int,
    ) -> dict[str, Any]:
        metadata_body = await self._request(
            user_id=user_id,
            method="GET",
            path=f"/me/messages/{message_id}/attachments/{attachment_id}",
            params={"$select": "id,name,contentType,size,contentBytes"},
        )

        name = str(metadata_body.get("name") or "")
        size = int(metadata_body.get("size") or 0)
        extension = ""
        if "." in name:
            extension = "." + name.rsplit(".", 1)[-1].lower()

        from app.config import ALLOWED_ATTACHMENT_EXTENSIONS

        if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise OutlookIntegrationError(
                f"Unsupported attachment type: {extension or 'unknown'}",
                code="outlook_attachment_unsupported",
            )
        if size > max_bytes:
            raise OutlookIntegrationError(
                f"Attachment exceeds maxBytes limit ({max_bytes}).",
                code="outlook_attachment_too_large",
            )

        content_bytes = metadata_body.get("contentBytes")
        if not isinstance(content_bytes, str):
            raise OutlookIntegrationError(
                "Attachment content unavailable",
                code="outlook_attachment_unavailable",
            )

        import base64

        raw = base64.b64decode(content_bytes)
        if len(raw) > max_bytes:
            raise OutlookIntegrationError(
                f"Attachment exceeds maxBytes limit ({max_bytes}).",
                code="outlook_attachment_too_large",
            )

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

        return {
            "attachmentId": attachment_id,
            "fileName": name,
            "contentType": metadata_body.get("contentType"),
            "size": size,
            "text": text,
        }
