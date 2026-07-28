"""Model roles used by Sabio's agent graph."""

import os

from google.adk.models.lite_llm import LiteLlm

_DEFAULT_SPECIALIST_MODEL = "openai/gpt-4o-mini"


def specialist_model() -> LiteLlm:
    """Use a fast model for bounded retrieval; the root handles synthesis."""
    return LiteLlm(
        model=os.getenv("SABIO_SPECIALIST_MODEL", _DEFAULT_SPECIALIST_MODEL)
    )
