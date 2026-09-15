"""
watsonx.py — Thin IBM watsonx.ai wrapper for the AI Advisor module (Member 4).

This module provides a single function, ``query_watsonx``, that sends a
prompt to IBM watsonx.ai (granite-13b-instruct-v2 by default) and returns
the generated text.

Graceful fallback
-----------------
If any of the three required environment variables are absent, or if the
``ibm-watsonx-ai`` package is not installed, ``query_watsonx`` returns
``None`` silently.  All callers (explainer.py, capa.py) fall back to their
deterministic template output in that case — the application remains fully
functional without watsonx credentials.

Required environment variables (copy from src/.env.example):
    WATSONX_API_KEY      — IBM Cloud API key
    WATSONX_PROJECT_ID   — watsonx.ai project ID
    WATSONX_URL          — service endpoint, e.g. https://us-south.ml.cloud.ibm.com

Usage:
    from src.ai.watsonx import query_watsonx

    text = query_watsonx(prompt="Explain this risk score …")
    if text is not None:
        # use AI-enriched text
    else:
        # fall back to template
"""

from __future__ import annotations

import os
from typing import Optional


# ---------------------------------------------------------------------------
# Default model — IBM Granite 13B Instruct v2 (available in watsonx.ai)
# Override by setting WATSONX_MODEL_ID in the environment.
# ---------------------------------------------------------------------------

_DEFAULT_MODEL_ID = "ibm/granite-13b-instruct-v2"

# Generation parameters — conservative settings for structured clinical text.
_GEN_PARAMS: dict = {
    "max_new_tokens": 400,
    "min_new_tokens": 40,
    "temperature":    0.3,      # low temperature → more deterministic output
    "top_p":          0.85,
    "repetition_penalty": 1.1,
}


def query_watsonx(
    prompt: str,
    model_id: str | None = None,
) -> Optional[str]:
    """Send *prompt* to IBM watsonx.ai and return the generated text.

    Returns ``None`` (without raising) if:
    - Any required environment variable is missing.
    - The ``ibm-watsonx-ai`` package is not installed.
    - The API call fails for any reason (network, auth, quota, etc.).

    Args:
        prompt:   The full prompt string to send to the model.
        model_id: Optional model override.  Defaults to
                  ``ibm/granite-13b-instruct-v2``.

    Returns:
        Generated text string, or ``None`` on any failure.
    """
    api_key    = os.getenv("WATSONX_API_KEY", "").strip()
    project_id = os.getenv("WATSONX_PROJECT_ID", "").strip()
    url        = os.getenv("WATSONX_URL", "").strip()

    # All three env vars must be present and non-empty.
    if not api_key or not project_id or not url:
        return None

    try:
        from ibm_watsonx_ai import Credentials                          # type: ignore
        from ibm_watsonx_ai.foundation_models import ModelInference     # type: ignore
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as P  # type: ignore
    except ImportError:
        # ibm-watsonx-ai not installed — silent fallback.
        return None

    try:
        credentials = Credentials(api_key=api_key, url=url)
        model = ModelInference(
            model_id   = model_id or os.getenv("WATSONX_MODEL_ID", _DEFAULT_MODEL_ID),
            credentials= credentials,
            project_id = project_id,
            params     = {
                P.MAX_NEW_TOKENS:       _GEN_PARAMS["max_new_tokens"],
                P.MIN_NEW_TOKENS:       _GEN_PARAMS["min_new_tokens"],
                P.TEMPERATURE:          _GEN_PARAMS["temperature"],
                P.TOP_P:                _GEN_PARAMS["top_p"],
                P.REPETITION_PENALTY:   _GEN_PARAMS["repetition_penalty"],
            },
        )
        response = model.generate_text(prompt=prompt)
        # ModelInference.generate_text returns a plain string.
        return response.strip() if isinstance(response, str) else None

    except Exception:  # noqa: BLE001 — intentional catch-all; never crash the UI
        return None


def watsonx_available() -> bool:
    """Return True if watsonx credentials are configured and the SDK is installed.

    Useful for displaying a status badge in the dashboard.
    """
    api_key    = os.getenv("WATSONX_API_KEY", "").strip()
    project_id = os.getenv("WATSONX_PROJECT_ID", "").strip()
    url        = os.getenv("WATSONX_URL", "").strip()
    if not api_key or not project_id or not url:
        return False
    try:
        import ibm_watsonx_ai  # noqa: F401  # type: ignore
        return True
    except ImportError:
        return False
