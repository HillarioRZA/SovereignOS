"""
Base Interface untuk LLM Adapters Sovereign OS.
Menetapkan kontrak pemanggilan REST/SSE tanpa framework pihak ketiga.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseLLMAdapter(ABC):
    """Kontrak abstrak dasar untuk seluruh adapter LLM murni native."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
        thinking_level: str = "medium",
    ) -> Dict[str, Any]:
        """Menjalankan pemanggilan completion teks secara asinkron.
        
        Mengembalikan kamus:
            {
                "content": str,
                "reasoning": str,
                "prompt_tokens": int,
                "cached_prompt_tokens": int,
                "completion_tokens": int,
                "model": str,
                "provider": str,
            }
        """
        pass
