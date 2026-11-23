"""Swappable structured + multimodal Cloud LLM provider (Gemini default)."""
from __future__ import annotations

import os
from typing import List, Optional, Protocol, Tuple, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
FALLBACK_GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.7-flash")


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
    ) -> T: ...

    def generate_structured_with_images(
        self,
        prompt: str,
        images: List[Tuple[bytes, str]],
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
    ) -> T: ...


class GeminiProvider:
    """Google Gemini provider using the official `google-genai` SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "")
        ).strip()
        self._model = (
            model or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        ).strip()

    @property
    def model_name(self) -> str:
        return self._model

    def _client(self):
        if not self._api_key:
            raise ValueError(
                "Gemini API key missing: set GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment"
            )
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415

        http_options = types.HttpOptions(
            timeout=35_000,
            retry_options=types.HttpRetryOptions(
                attempts=2,
                initial_delay=1.0,
                max_delay=3.0,
            ),
        )
        return genai.Client(api_key=self._api_key, http_options=http_options)

    def _call(
        self,
        contents,
        schema: Type[T],
        system_instruction: Optional[str],
    ) -> T:
        from google.genai import types  # noqa: PLC0415

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system_instruction,
            temperature=0.1,
        )
        client = self._client()
        models_to_try = [self._model] + [m for m in FALLBACK_GEMINI_MODELS if m != self._model]
        last_exc: Optional[Exception] = None
        resp = None
        try:
            for idx, model_name in enumerate(models_to_try):
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    self._model = model_name
                    break
                except Exception as exc:  # noqa: BLE001
                    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                    msg = str(exc)
                    is_transient = status in (429, 503) or "503" in msg or "UNAVAILABLE" in msg or "429" in msg
                    if is_transient and idx < len(models_to_try) - 1:
                        last_exc = exc
                        continue
                    raise
        finally:
            close_fn = getattr(client, "close", None)
            if callable(close_fn):
                close_fn()
        if resp is None:
            raise ValueError(f"All Gemini models failed: {last_exc}") from last_exc
        raw_text = getattr(resp, "text", None)
        if not raw_text:
            raise ValueError(f"Empty structured response from Gemini model {self._model!r}")
        return schema.model_validate_json(raw_text)

    def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
    ) -> T:
        return self._call(prompt, schema, system_instruction)

    def generate_structured_with_images(
        self,
        prompt: str,
        images: List[Tuple[bytes, str]],
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
    ) -> T:
        from google.genai import types  # noqa: PLC0415

        parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images]
        contents = [prompt, *parts]
        return self._call(contents, schema, system_instruction)


def get_default_provider() -> LLMProvider:
    """Return the configured LLMProvider (defaults to GeminiProvider)."""
    provider_name = (os.environ.get("GENIE_LLM_PROVIDER") or "gemini").strip().lower()
    if provider_name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unsupported GENIE_LLM_PROVIDER: {provider_name!r}")
