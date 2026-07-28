"""Validated request and attachment models for the chat API."""

import base64
import binascii
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from backend.chat.constants import (
    MAX_ATTACHMENTS,
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    TITLE_CHARS,
)

ChatLocale = Literal["en", "es"]


class ContextItem(BaseModel):
    """A file or highlighted excerpt explicitly attached from the code panel."""

    path: str = Field(min_length=1, max_length=1024)
    start_line: int | None = None
    end_line: int | None = None
    content: str = Field(max_length=250_000)


def decode_image_data(data_url: str, mime_type: str) -> bytes:
    prefix = f"data:{mime_type};base64,"
    if not data_url.startswith(prefix):
        raise ValueError("image data URL does not match its MIME type")
    try:
        raw = base64.b64decode(data_url[len(prefix) :], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image data is not valid base64") from exc
    if not raw:
        raise ValueError("image cannot be empty")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image is larger than 5 MB")

    signatures = {
        "image/jpeg": raw.startswith(b"\xff\xd8\xff"),
        "image/png": raw.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": raw.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": (
            len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
        ),
    }
    if not signatures.get(mime_type, False):
        raise ValueError("image bytes do not match the declared MIME type")
    return raw


class ImageAttachment(BaseModel):
    kind: Literal["image"]
    name: str = Field(min_length=1, max_length=255)
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "image/gif"]
    size: int = Field(gt=0, le=MAX_IMAGE_BYTES)
    data_url: str = Field(max_length=7_100_000)

    @model_validator(mode="after")
    def validate_image(self):
        raw = decode_image_data(self.data_url, self.mime_type)
        if len(raw) != self.size:
            raise ValueError("image size does not match its data")
        return self


class RepositoryAttachment(BaseModel):
    kind: Literal["repository"]
    repo_id: Literal["core", "knots", "bips", "secp256k1"]
    label: str = Field(min_length=1, max_length=120)


class PersonAttachment(BaseModel):
    kind: Literal["person"]
    person_id: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=200)
    github_username: str | None = Field(default=None, max_length=100)
    bitcointalk_username: str | None = Field(default=None, max_length=100)


ChatAttachment = Annotated[
    ImageAttachment | RepositoryAttachment | PersonAttachment,
    Field(discriminator="kind"),
]


class ChatRequest(BaseModel):
    session_id: UUID
    run_id: UUID = Field(default_factory=uuid4)
    locale: ChatLocale = "en"
    message: str = Field(min_length=1, max_length=16_000)
    context: list[ContextItem] = Field(default_factory=list, max_length=8)
    attachments: list[ChatAttachment] = Field(
        default_factory=list,
        max_length=MAX_ATTACHMENTS,
    )

    @model_validator(mode="after")
    def validate_attachment_counts(self):
        image_count = sum(
            isinstance(attachment, ImageAttachment) for attachment in self.attachments
        )
        if image_count > MAX_IMAGES:
            raise ValueError(f"at most {MAX_IMAGES} images can be attached")
        return self


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_CHARS)


class StopChatRequest(BaseModel):
    session_id: UUID
    run_id: UUID
