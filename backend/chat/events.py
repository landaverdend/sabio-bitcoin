"""Translate persisted Google ADK events into Sabio's frontend event shape."""

import base64
from urllib.parse import urlparse

from google.adk.events.event import Event

from backend.chat.constants import DISPLAY_MESSAGE_STATE_KEY


def legacy_display_text(text: str) -> str:
    """Recover visible text from sessions created before display metadata."""
    separator = "\n\n---\n\n"
    return text.rsplit(separator, 1)[-1] if separator in text else text


def history_attachments(event: Event, display: dict) -> list[dict]:
    image_parts = [
        part.inline_data
        for part in (event.content.parts if event.content else [])
        if part.inline_data and part.inline_data.data and part.inline_data.mime_type
    ]
    image_index = 0
    attachments = []

    for index, item in enumerate(display.get("attachments", [])):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        attachment_id = f"{event.id}:attachment:{index}"
        if kind == "image":
            if image_index >= len(image_parts):
                continue
            image = image_parts[image_index]
            image_index += 1
            attachments.append(
                {
                    "id": attachment_id,
                    "kind": "image",
                    "name": item.get("name") or "Attached image",
                    "mimeType": image.mime_type,
                    "size": len(image.data),
                    "dataUrl": (
                        f"data:{image.mime_type};base64,"
                        f"{base64.b64encode(image.data).decode('ascii')}"
                    ),
                }
            )
        elif kind == "repository" and item.get("repo_id") and item.get("label"):
            attachments.append(
                {
                    "id": attachment_id,
                    "kind": "repository",
                    "repoId": item["repo_id"],
                    "label": item["label"],
                }
            )
        elif kind == "person" and item.get("person_id") and item.get("label"):
            attachments.append(
                {
                    "id": attachment_id,
                    "kind": "person",
                    "personId": item["person_id"],
                    "label": item["label"],
                    "githubUsername": item.get("github_username"),
                    "bitcointalkUsername": item.get("bitcointalk_username"),
                }
            )

    return attachments


def source_reference(response: dict) -> dict | None:
    """Build a source event from a validated read_file tool result."""
    required = ("repo", "path", "ref", "start_line", "end_line", "github_url")
    if not all(key in response for key in required):
        return None
    if not (
        isinstance(response["repo"], str)
        and isinstance(response["path"], str)
        and isinstance(response["ref"], str)
        and isinstance(response["start_line"], int)
        and isinstance(response["end_line"], int)
        and isinstance(response["github_url"], str)
    ):
        return None
    if response["start_line"] < 1 or response["end_line"] < response["start_line"]:
        return None
    return {
        "type": "source",
        "repo": response["repo"],
        "path": response["path"],
        "ref": response["ref"],
        "start_line": response["start_line"],
        "end_line": response["end_line"],
        "github_url": response["github_url"],
    }


def communication_reference(response: dict) -> dict | None:
    """Build a citable archive reference from one complete message result."""
    message_id = response.get("id")
    channel = response.get("channel")
    body = response.get("body")
    url = response.get("url")
    if (
        not isinstance(message_id, (int, str))
        or isinstance(message_id, bool)
        or not isinstance(channel, str)
        or not isinstance(body, str)
        or not isinstance(url, str)
        or not url.startswith(("http://", "https://"))
    ):
        return None

    compact_body = " ".join(body.split())
    excerpt = compact_body[:360]
    if len(compact_body) > len(excerpt):
        excerpt += "…"

    return {
        "type": "communication_source",
        "message_id": str(message_id),
        "channel": channel,
        "author": (
            response.get("author") if isinstance(response.get("author"), str) else None
        ),
        "title": (
            response.get("title") if isinstance(response.get("title"), str) else None
        ),
        "posted_at": (
            response.get("posted_at")
            if isinstance(response.get("posted_at"), str)
            else None
        ),
        "excerpt": excerpt,
        "source_url": url,
    }


def irc_context_references(response: dict) -> list[dict]:
    """Build source cards for each validated event in get_irc_context."""
    raw_events = response.get("events")
    if not isinstance(raw_events, list):
        return []

    references = []
    seen_ids: set[str] = set()
    for event in raw_events[:25]:
        if not isinstance(event, dict):
            continue
        reference = communication_reference(event)
        if reference is None or reference["message_id"] in seen_ids:
            continue
        seen_ids.add(reference["message_id"])
        references.append(reference)
    return references


def github_discussion_reference(response: dict) -> dict | None:
    """Build a source event from one exact get_pr_discussion_item result."""
    repo = response.get("repo")
    pr_number = response.get("pr_number")
    kind = response.get("kind")
    item_id = response.get("id")
    body = response.get("body")
    url = response.get("url")
    url_host = urlparse(url).hostname if isinstance(url, str) else None

    if not isinstance(repo, str) or not repo:
        return None
    if (
        not isinstance(pr_number, int)
        or isinstance(pr_number, bool)
        or pr_number < 1
    ):
        return None
    if kind not in {
        "pull_request",
        "conversation_comment",
        "review",
        "review_comment",
    }:
        return None
    if not isinstance(item_id, (int, str)) or isinstance(item_id, bool):
        return None
    if not isinstance(body, str) or not body.strip():
        return None
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    if url_host not in {"github.com", "www.github.com"}:
        return None

    compact_body = " ".join(body.split())
    excerpt = compact_body[:360]
    if len(compact_body) > len(excerpt):
        excerpt += "…"

    line = response.get("line")
    return {
        "type": "github_discussion_source",
        "repo": repo,
        "pr_number": pr_number,
        "pr_title": (
            response.get("pr_title")
            if isinstance(response.get("pr_title"), str)
            else None
        ),
        "kind": kind,
        "item_id": str(item_id),
        "author": (
            response.get("author") if isinstance(response.get("author"), str) else None
        ),
        "created_at": (
            response.get("created_at")
            if isinstance(response.get("created_at"), str)
            else None
        ),
        "excerpt": excerpt,
        "path": (
            response.get("path") if isinstance(response.get("path"), str) else None
        ),
        "line": (
            line
            if isinstance(line, int) and not isinstance(line, bool) and line > 0
            else None
        ),
        "source_url": url,
    }


def web_references(response: dict) -> list[dict]:
    """Build source-card events only from search_web's cited URLs."""
    raw_sources = response.get("sources")
    if not isinstance(raw_sources, list):
        return []

    references = []
    seen_urls: set[str] = set()
    for source in raw_sources[:8]:
        if not isinstance(source, dict):
            continue
        title = source.get("title")
        url = source.get("url")
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(url, str)
            or not url.startswith(("http://", "https://"))
            or url in seen_urls
        ):
            continue
        seen_urls.add(url)
        references.append(
            {
                "type": "web_source",
                "title": title.strip(),
                "source_url": url,
            }
        )
    return references


def research_references(response: dict) -> list[dict]:
    """Validate compact source payloads returned by a specialist tool."""
    raw_sources = response.get("sources")
    if not isinstance(raw_sources, list):
        return []

    references = []
    seen: set[tuple[str, str]] = set()
    for raw_source in raw_sources[:50]:
        if not isinstance(raw_source, dict):
            continue
        source_type = raw_source.get("type")
        reference = None
        identity = None

        if source_type == "source":
            reference = source_reference(raw_source)
            if reference:
                identity = (
                    source_type,
                    f"{reference['repo']}:{reference['path']}:{reference['ref']}:"
                    f"{reference['start_line']}:{reference['end_line']}",
                )
        elif source_type == "communication_source":
            message_id = raw_source.get("message_id")
            channel = raw_source.get("channel")
            excerpt = raw_source.get("excerpt")
            source_url = raw_source.get("source_url")
            if (
                isinstance(message_id, str)
                and message_id
                and isinstance(channel, str)
                and channel
                and isinstance(excerpt, str)
                and isinstance(source_url, str)
                and source_url.startswith(("http://", "https://"))
            ):
                reference = {
                    "type": source_type,
                    "message_id": message_id,
                    "channel": channel,
                    "author": (
                        raw_source.get("author")
                        if isinstance(raw_source.get("author"), str)
                        else None
                    ),
                    "title": (
                        raw_source.get("title")
                        if isinstance(raw_source.get("title"), str)
                        else None
                    ),
                    "posted_at": (
                        raw_source.get("posted_at")
                        if isinstance(raw_source.get("posted_at"), str)
                        else None
                    ),
                    "excerpt": excerpt[:361],
                    "source_url": source_url,
                }
                identity = (source_type, message_id)
        elif source_type == "github_discussion_source":
            source_url = raw_source.get("source_url")
            item_id = raw_source.get("item_id")
            if (
                isinstance(source_url, str)
                and source_url.startswith(("http://", "https://"))
                and isinstance(item_id, str)
                and item_id
            ):
                reference = {
                    key: raw_source.get(key)
                    for key in (
                        "author",
                        "created_at",
                        "excerpt",
                        "item_id",
                        "kind",
                        "line",
                        "path",
                        "pr_number",
                        "pr_title",
                        "repo",
                        "source_url",
                        "type",
                    )
                }
                identity = (source_type, source_url)
        elif source_type == "web_source":
            title = raw_source.get("title")
            source_url = raw_source.get("source_url")
            if (
                isinstance(title, str)
                and title
                and isinstance(source_url, str)
                and source_url.startswith(("http://", "https://"))
            ):
                reference = {
                    "type": source_type,
                    "title": title,
                    "source_url": source_url,
                }
                identity = (source_type, source_url)

        if reference is None or identity is None or identity in seen:
            continue
        seen.add(identity)
        references.append(reference)

    return references


def event_payloads(event: Event) -> list[dict]:
    """Turn one ADK event into Sabio's shared live/history event shape."""
    if event.author == "user":
        display = (event.actions.state_delta or {}).get(DISPLAY_MESSAGE_STATE_KEY)
        if isinstance(display, dict) and isinstance(display.get("message"), str):
            context = [
                {
                    "id": f"{event.id}:{index}",
                    "path": item.get("path", ""),
                    "startLine": item.get("start_line"),
                    "endLine": item.get("end_line"),
                    "content": "",
                }
                for index, item in enumerate(display.get("context", []))
                if isinstance(item, dict) and item.get("path")
            ]
            return [
                {
                    "type": "user_message",
                    "message": display["message"],
                    "context": context,
                    "attachments": history_attachments(event, display),
                }
            ]

        if event.content and event.content.parts:
            text = "".join(part.text or "" for part in event.content.parts)
            return [
                {
                    "type": "user_message",
                    "message": legacy_display_text(text),
                    "context": [],
                    "attachments": [],
                }
            ]
        return []

    if not event.content or not event.content.parts:
        return []

    payloads = []
    for part in event.content.parts:
        if part.function_call:
            if part.function_call.name == "transfer_to_agent":
                payloads.append(
                    {
                        "type": "handoff",
                        "to": part.function_call.args.get("agent_name"),
                    }
                )
            else:
                payloads.append(
                    {
                        "type": "tool_call",
                        "author": event.author,
                        "tool": part.function_call.name,
                        "args": part.function_call.args,
                    }
                )
        elif part.function_response:
            if part.function_response.name == "transfer_to_agent":
                continue
            payloads.append(
                {
                    "type": "tool_result",
                    "author": event.author,
                    "tool": part.function_response.name,
                }
            )
            response = part.function_response.response or {}
            if part.function_response.name == "read_file":
                source = source_reference(response)
                if source is not None:
                    payloads.append(source)
            elif part.function_response.name in {"get_message", "get_irc_event"}:
                source = communication_reference(response)
                if source is not None:
                    payloads.append(source)
            elif part.function_response.name == "get_irc_context":
                payloads.extend(irc_context_references(response))
            elif part.function_response.name == "get_pr_discussion_item":
                source = github_discussion_reference(response)
                if source is not None:
                    payloads.append(source)
            elif part.function_response.name == "search_web":
                payloads.extend(web_references(response))
            elif part.function_response.name in {
                "sabio_comms",
                "sabio_irc",
                "sabio_repos",
            }:
                payloads.extend(research_references(response))
        elif part.text:
            payloads.append(
                {
                    "type": "text",
                    "author": event.author,
                    "text": part.text,
                }
            )
    return payloads
