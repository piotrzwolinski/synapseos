"""
Unified LLM Provider Abstraction for Multi-LLM Debate.

Each provider sends the raw PDF as a native document attachment —
no text extraction or preprocessing. The LLM analyzes tables,
diagrams, and specs directly.
"""

import base64
import os
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from api_keys import api_keys_manager


@dataclass
class LLMResponse:
    provider: str
    content: str
    usage_tokens: int = 0
    duration_s: float = 0.0
    error: Optional[str] = None


class LLMProvider(ABC):
    name: str
    label: str

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_mime_type: str = "application/pdf",
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> LLMResponse:
        """Synchronous generation. Called from thread pool."""
        ...

    def is_configured(self) -> bool:
        return api_keys_manager.get_key(self.name) is not None


class GeminiProvider(LLMProvider):
    name = "gemini"
    label = "Gemini"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_mime_type: str = "application/pdf",
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> LLMResponse:
        from google import genai
        from google.genai import types

        api_key = api_keys_manager.get_key("gemini")
        if not api_key:
            return LLMResponse(provider=self.name, content="", error="Gemini API key not configured")

        client = genai.Client(api_key=api_key)
        model = "gemini-2.0-flash"
        t0 = time.time()

        try:
            parts = []
            if pdf_bytes:
                file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                parts.append(types.Part(
                    inline_data=types.Blob(
                        mime_type=pdf_mime_type,
                        data=file_b64,
                    )
                ))
            parts.append(types.Part(text=f"{system_prompt}\n\n{user_prompt}"))

            response = client.models.generate_content(
                model=model,
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return LLMResponse(
                provider=self.name,
                content=response.text.strip(),
                duration_s=round(time.time() - t0, 2),
            )
        except Exception as e:
            return LLMResponse(
                provider=self.name, content="",
                error=str(e), duration_s=round(time.time() - t0, 2),
            )


class OpenAIProvider(LLMProvider):
    name = "openai"
    label = "GPT-5.2"

    _uploaded_file_id: Optional[str] = None

    def _upload_pdf(self, client, pdf_bytes: bytes) -> Optional[str]:
        """Upload PDF via Files API for reliable processing."""
        if self._uploaded_file_id:
            return self._uploaded_file_id
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            with open(tmp.name, "rb") as f:
                file_obj = client.files.create(file=f, purpose="user_data")
            os.unlink(tmp.name)
        OpenAIProvider._uploaded_file_id = file_obj.id
        return file_obj.id

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_mime_type: str = "application/pdf",
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> LLMResponse:
        from openai import OpenAI

        api_key = api_keys_manager.get_key("openai")
        if not api_key:
            return LLMResponse(provider=self.name, content="", error="OpenAI API key not configured")

        client = OpenAI(api_key=api_key)
        t0 = time.time()

        try:
            user_content = []
            if pdf_bytes:
                file_id = self._upload_pdf(client, pdf_bytes)
                if file_id:
                    user_content.append({
                        "type": "input_file",
                        "file_id": file_id,
                    })
            user_content.append({"type": "input_text", "text": user_prompt})

            response = client.responses.create(
                model="gpt-5.2",
                instructions=system_prompt,
                input=[{"role": "user", "content": user_content}],
                text={"format": {"type": "json_object"}},
                max_output_tokens=max_tokens,
            )
            text = response.output_text or ""
            if not text:
                # Fallback: inspect raw output items
                for item in getattr(response, "output", []):
                    for block in getattr(item, "content", []):
                        if getattr(block, "text", None):
                            text = block.text
                            break
            return LLMResponse(
                provider=self.name,
                content=text.strip(),
                duration_s=round(time.time() - t0, 2),
            )
        except Exception as e:
            return LLMResponse(
                provider=self.name, content="",
                error=str(e), duration_s=round(time.time() - t0, 2),
            )


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    label = "Claude"

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_mime_type: str = "application/pdf",
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> LLMResponse:
        import anthropic

        api_key = api_keys_manager.get_key("anthropic")
        if not api_key:
            return LLMResponse(provider=self.name, content="", error="Anthropic API key not configured")

        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.time()

        try:
            user_content = []
            if pdf_bytes:
                file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                user_content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": pdf_mime_type,
                        "data": file_b64,
                    },
                })
            user_content.append({"type": "text", "text": user_prompt})

            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text if response.content else ""
            return LLMResponse(
                provider=self.name,
                content=text.strip(),
                duration_s=round(time.time() - t0, 2),
            )
        except Exception as e:
            return LLMResponse(
                provider=self.name, content="",
                error=str(e), duration_s=round(time.time() - t0, 2),
            )


class GeminiProProvider(GeminiProvider):
    """Gemini 3 Pro Preview — highest-tier Gemini for audit tasks."""
    name = "gemini_pro"
    label = "Gemini 3 Pro"

    def is_configured(self) -> bool:
        return api_keys_manager.get_key("gemini") is not None

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_mime_type: str = "application/pdf",
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> LLMResponse:
        from google import genai
        from google.genai import types

        api_key = api_keys_manager.get_key("gemini")
        if not api_key:
            return LLMResponse(provider=self.name, content="", error="Gemini API key not configured")

        client = genai.Client(api_key=api_key)
        model = "gemini-3-pro-preview"
        t0 = time.time()

        try:
            parts = []
            if pdf_bytes:
                file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                parts.append(types.Part(
                    inline_data=types.Blob(
                        mime_type=pdf_mime_type,
                        data=file_b64,
                    )
                ))
            parts.append(types.Part(text=f"{system_prompt}\n\n{user_prompt}"))

            response = client.models.generate_content(
                model=model,
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return LLMResponse(
                provider=self.name,
                content=response.text.strip(),
                duration_s=round(time.time() - t0, 2),
            )
        except Exception as e:
            return LLMResponse(
                provider=self.name, content="",
                error=str(e), duration_s=round(time.time() - t0, 2),
            )


class AnthropicOpusProvider(AnthropicProvider):
    """Claude Opus 4.6 — highest-tier Anthropic for audit tasks."""
    name = "anthropic_opus"
    label = "Claude Opus 4.6"

    def is_configured(self) -> bool:
        return api_keys_manager.get_key("anthropic") is not None

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: Optional[bytes] = None,
        pdf_mime_type: str = "application/pdf",
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> LLMResponse:
        import anthropic

        api_key = api_keys_manager.get_key("anthropic")
        if not api_key:
            return LLMResponse(provider=self.name, content="", error="Anthropic API key not configured")

        client = anthropic.Anthropic(api_key=api_key)
        t0 = time.time()

        try:
            user_content = []
            if pdf_bytes:
                file_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                user_content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": pdf_mime_type,
                        "data": file_b64,
                    },
                })
            user_content.append({"type": "text", "text": user_prompt})

            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text if response.content else ""
            return LLMResponse(
                provider=self.name,
                content=text.strip(),
                duration_s=round(time.time() - t0, 2),
            )
        except Exception as e:
            return LLMResponse(
                provider=self.name, content="",
                error=str(e), duration_s=round(time.time() - t0, 2),
            )


def get_available_providers() -> list[LLMProvider]:
    """Return all providers that have API keys configured."""
    all_providers = [GeminiProvider(), OpenAIProvider(), AnthropicProvider()]
    return [p for p in all_providers if p.is_configured()]


def get_all_providers() -> list[LLMProvider]:
    """Return all provider instances regardless of configuration."""
    return [GeminiProvider(), OpenAIProvider(), AnthropicProvider()]


def get_audit_providers() -> list[LLMProvider]:
    """Return high-tier providers for graph audit tasks."""
    all_providers = [GeminiProProvider(), OpenAIProvider(), AnthropicOpusProvider()]
    return [p for p in all_providers if p.is_configured()]
