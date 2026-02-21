"""Unified LLM Router — dual-provider abstraction for Gemini + OpenAI.

Routes LLM calls to Google Gemini or OpenAI GPT based on model prefix (gpt-* / gemini-*):
  - gemini-* → Google GenAI SDK
  - gpt-*   → OpenAI Responses API

All callers use a single `llm_call()` function with a unified response format.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from api_keys import api_keys_manager

logger = logging.getLogger(__name__)

# Available models for the UI switcher
AVAILABLE_MODELS = [
    {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash", "provider": "gemini"},
    {"id": "gemini-3-pro-preview", "label": "Gemini 3 Pro", "provider": "gemini"},
    {"id": "gpt-5.2", "label": "GPT-5.2", "provider": "openai"},
]

DEFAULT_MODEL = "gpt-5.2"


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0
    error: Optional[str] = None


def _call_gemini(
    model: str,
    system_prompt: Optional[str],
    user_prompt: str,
    json_mode: bool,
    temperature: float,
    max_output_tokens: Optional[int],
) -> LLMResult:
    from google import genai
    from google.genai import types

    api_key = api_keys_manager.get_key("gemini")
    if not api_key:
        return LLMResult(text="", error="GEMINI_API_KEY not set")

    client = genai.Client(api_key=api_key)
    t0 = time.time()

    config_kwargs: dict = {}
    if system_prompt:
        config_kwargs["system_instruction"] = system_prompt
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    config_kwargs["temperature"] = temperature
    if max_output_tokens:
        config_kwargs["max_output_tokens"] = max_output_tokens

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_prompt)],
                )
            ],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text = response.text or ""
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_s=round(time.time() - t0, 2),
        )
    except Exception as e:
        logger.error(f"Gemini API error ({model}): {e}")
        return LLMResult(
            text="",
            error=str(e),
            duration_s=round(time.time() - t0, 2),
        )


def _call_openai(
    model: str,
    system_prompt: Optional[str],
    user_prompt: str,
    json_mode: bool,
    temperature: float,
    max_output_tokens: Optional[int],
) -> LLMResult:
    from openai import OpenAI

    api_key = api_keys_manager.get_key("openai")
    if not api_key:
        return LLMResult(text="", error="OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    t0 = time.time()

    kwargs: dict = {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": user_prompt}]}],
        "temperature": temperature,
    }
    if system_prompt:
        kwargs["instructions"] = system_prompt
    if json_mode:
        kwargs["text"] = {"format": {"type": "json_object"}}
    if max_output_tokens:
        kwargs["max_output_tokens"] = max_output_tokens

    try:
        response = client.responses.create(**kwargs)

        text = response.output_text or ""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_s=round(time.time() - t0, 2),
        )
    except Exception as e:
        logger.error(f"OpenAI API error ({model}): {e}")
        return LLMResult(
            text="",
            error=str(e),
            duration_s=round(time.time() - t0, 2),
        )


def llm_call(
    model: str,
    user_prompt: str,
    system_prompt: Optional[str] = None,
    json_mode: bool = True,
    temperature: float = 0.0,
    max_output_tokens: Optional[int] = None,
) -> LLMResult:
    """Route an LLM call to the appropriate provider based on model name."""
    if model.startswith("gpt-"):
        return _call_openai(model, system_prompt, user_prompt, json_mode, temperature, max_output_tokens)
    else:
        return _call_gemini(model, system_prompt, user_prompt, json_mode, temperature, max_output_tokens)
