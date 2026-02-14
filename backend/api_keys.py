"""
API Key Management for Multi-LLM Test Generator.

Reads API keys exclusively from environment variables.
Keys are never exposed in full via the API — only masked versions are returned.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))


PROVIDERS = {
    "openai": {"env_var": "OPENAI_API_KEY", "label": "OpenAI"},
    "anthropic": {"env_var": "ANTHROPIC_API_KEY", "label": "Anthropic"},
    "gemini": {"env_var": "GEMINI_API_KEY", "label": "Google Gemini"},
}


class ApiKeyStatus(BaseModel):
    provider: str
    label: str
    configured: bool
    masked_key: Optional[str] = None


class ApiKeysManager:

    def get_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider from environment variables."""
        env_var = PROVIDERS.get(provider, {}).get("env_var")
        if env_var:
            return os.getenv(env_var)
        return None

    def get_status(self) -> list[ApiKeyStatus]:
        """Get masked status for all providers."""
        result = []
        for provider, meta in PROVIDERS.items():
            key = self.get_key(provider)
            masked = None
            if key and len(key) > 8:
                masked = f"{key[:4]}...{key[-4:]}"
            elif key:
                masked = "***"
            result.append(ApiKeyStatus(
                provider=provider,
                label=meta["label"],
                configured=key is not None and len(key or "") > 0,
                masked_key=masked,
            ))
        return result

    def get_configured_providers(self) -> list[str]:
        """Return list of provider names that have keys configured."""
        return [s.provider for s in self.get_status() if s.configured]


api_keys_manager = ApiKeysManager()
