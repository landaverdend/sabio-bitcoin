"""Build model input and compact persisted display metadata."""

from google.genai import types

from backend.chat.constants import CONTEXT_ITEM_CHARS
from backend.chat.models import (
    ChatAttachment,
    ChatLocale,
    ContextItem,
    ImageAttachment,
    PersonAttachment,
    RepositoryAttachment,
    decode_image_data,
)

LANGUAGE_INSTRUCTIONS: dict[ChatLocale, str] = {
    "en": (
        "Respond in English. Keep source quotations in their original language. "
        "Do not translate code, command names, identifiers, or URLs."
    ),
    "es": (
        "Respond in Spanish. Keep source quotations in their original language and "
        "explain them in Spanish when useful. Do not translate code, command names, "
        "identifiers, or URLs. The archives and source code are primarily in English, "
        "so formulate tool searches in English when that will retrieve better results."
    ),
}


def build_prompt(
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment] | None = None,
    locale: ChatLocale = "en",
) -> str:
    attachments = attachments or []
    reference_blocks = []
    for attachment in attachments:
        if isinstance(attachment, RepositoryAttachment):
            reference_blocks.append(
                f"- Repository: {attachment.label} (`repo_name={attachment.repo_id}`)"
            )
        elif isinstance(attachment, PersonAttachment):
            identities = []
            if attachment.github_username:
                identities.append(f"GitHub @{attachment.github_username}")
            if attachment.bitcointalk_username:
                identities.append(f"BitcoinTalk {attachment.bitcointalk_username}")
            identity_text = f"; known as {', '.join(identities)}" if identities else ""
            reference_blocks.append(
                f"- Person: {attachment.label} "
                f"(`person_id={attachment.person_id}`{identity_text})"
            )

    image_count = sum(
        isinstance(attachment, ImageAttachment) for attachment in attachments
    )
    code_blocks = []
    for item in context:
        where = (
            f"{item.path} (lines {item.start_line}-{item.end_line})"
            if item.start_line
            else item.path
        )
        code_blocks.append(
            f"### {where}\n```\n{item.content[:CONTEXT_ITEM_CHARS]}\n```"
        )

    prompt_parts = [
        "Application language preference:\n" + LANGUAGE_INSTRUCTIONS[locale]
    ]
    if code_blocks:
        prompt_parts.append("Attached code context:\n\n" + "\n\n".join(code_blocks))
    if reference_blocks:
        prompt_parts.append(
            "Selected Sabio context (use these exact repository/person "
            "identifiers when calling tools):\n" + "\n".join(reference_blocks)
        )
    if image_count:
        prompt_parts.append(
            f"The user attached {image_count} "
            f"image{'s' if image_count != 1 else ''}. "
            "Inspect the image content directly when answering."
        )

    return "\n\n".join(prompt_parts) + "\n\n---\n\n" + message


def build_content(
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment],
    locale: ChatLocale = "en",
) -> types.Content:
    parts = [
        types.Part(
            text=build_prompt(
                message,
                context,
                attachments,
                locale,
            )
        )
    ]
    for attachment in attachments:
        if isinstance(attachment, ImageAttachment):
            parts.append(
                types.Part.from_bytes(
                    data=decode_image_data(
                        attachment.data_url,
                        attachment.mime_type,
                    ),
                    mime_type=attachment.mime_type,
                )
            )
    return types.Content(role="user", parts=parts)


def display_message(
    message: str,
    context: list[ContextItem],
    attachments: list[ChatAttachment] | None = None,
) -> dict:
    """Build small user-facing metadata for the persisted ADK user event."""
    attachment_metadata = []
    for attachment in attachments or []:
        if isinstance(attachment, ImageAttachment):
            attachment_metadata.append(
                {
                    "kind": "image",
                    "name": attachment.name,
                    "mime_type": attachment.mime_type,
                    "size": attachment.size,
                }
            )
        elif isinstance(attachment, RepositoryAttachment):
            attachment_metadata.append(
                {
                    "kind": "repository",
                    "repo_id": attachment.repo_id,
                    "label": attachment.label,
                }
            )
        elif isinstance(attachment, PersonAttachment):
            attachment_metadata.append(
                {
                    "kind": "person",
                    "person_id": attachment.person_id,
                    "label": attachment.label,
                    "github_username": attachment.github_username,
                    "bitcointalk_username": attachment.bitcointalk_username,
                }
            )

    return {
        "message": message,
        "context": [
            {
                "path": item.path,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in context
        ],
        # Image bytes already live in the persisted ADK content parts. Keep
        # only display metadata here instead of duplicating base64 in state.
        "attachments": attachment_metadata,
    }
