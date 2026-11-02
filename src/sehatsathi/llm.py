"""Optional LLM layer — behind an interface, OFF by default.

The deterministic core is the product. An LLM may only *rephrase*
reminder text for warmth when (a) the deployment has connectivity and
(b) the operator explicitly enables it with environment variables:

    SEHATSATHI_LLM_ENABLED=1
    SEHATSATHI_LLM_API_KEY=...       (never commit this)
    SEHATSATHI_LLM_BASE_URL=https://... (OpenAI-compatible endpoint)
    SEHATSATHI_LLM_MODEL=...

An LLM never decides priority, danger signs or dates — those stay
rule-based and auditable. If the LLM is unavailable, reminders fall
back silently to the deterministic templates.
"""
from __future__ import annotations

import os
from typing import Protocol


class ReminderEnhancer(Protocol):
    def enhance(self, text_en: str, text_hi: str) -> tuple[str, str]: ...


class NullEnhancer:
    """Default: deterministic templates, unchanged."""

    def enhance(self, text_en: str, text_hi: str) -> tuple[str, str]:
        return text_en, text_hi


def get_enhancer() -> ReminderEnhancer:
    if os.environ.get("SEHATSATHI_LLM_ENABLED") == "1" and \
            os.environ.get("SEHATSATHI_LLM_API_KEY"):
        return OpenAICompatibleEnhancer()
    return NullEnhancer()


class OpenAICompatibleEnhancer:
    """Thin, lazy wrapper — importing this module never needs network."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("SEHATSATHI_LLM_BASE_URL",
                                       "https://api.openai.com/v1")
        self.api_key = os.environ["SEHATSATHI_LLM_API_KEY"]
        self.model = os.environ.get("SEHATSATHI_LLM_MODEL", "gpt-4o-mini")

    def enhance(self, text_en: str, text_hi: str) -> tuple[str, str]:
        try:
            import json
            import urllib.request
            prompt = ("Rewrite this patient reminder more warmly, keeping ALL dates, "
                      "names and instructions exactly the same, simple words only:\n"
                      + text_en)
            body = json.dumps({
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                self.base_url.rstrip("/") + "/chat/completions", data=body,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip(), text_hi
        except Exception:
            return text_en, text_hi  # offline / failure → deterministic fallback
