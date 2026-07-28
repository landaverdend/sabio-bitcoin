"""Translate persisted Google ADK events into Sabio's frontend event shape."""

import base64

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
    """Build a citable archive reference from get_message's full result."""
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
            elif part.function_response.name == "get_message":
                source = communication_reference(response)
                if source is not None:
                    payloads.append(source)
            elif part.function_response.name == "search_web":
                payloads.extend(web_references(response))
        elif part.text:
            payloads.append(
                {
                    "type": "text",
                    "author": event.author,
                    "text": part.text,
                }
            )
    return payloads
