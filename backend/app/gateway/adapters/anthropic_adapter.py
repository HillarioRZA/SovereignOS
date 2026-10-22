"""
Anthropic Claude Messages API Adapter (Full-Native via HTTPX).
Mendukung Claude 3.5/3.7 Sonnet, prompt caching ephemera, dan extended thinking.
"""

from typing import Any, Dict, List, Optional
import httpx

from app.core.logger import logger
from app.gateway.adapters.base_adapter import BaseLLMAdapter
from app.gateway.cache_boundary import split_system_prompt_cache_boundary, SOVEREIGN_CACHE_BOUNDARY


class AnthropicAdapter(BaseLLMAdapter):
    """Adapter resmi REST untuk API Anthropic Messages."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.transport = transport

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "claude-3-7-sonnet-20250219",
        api_key: str = "",
        base_url: str = "https://api.anthropic.com/v1",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
        thinking_level: str = "medium",
    ) -> Dict[str, Any]:
        endpoint = f"{base_url.rstrip('/')}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
        }

        # Format system prompt dengan blok cache control
        system_blocks: List[Dict[str, Any]] = []
        if system_prompt:
            split_res = split_system_prompt_cache_boundary(system_prompt)
            if split_res:
                stable_prefix, dynamic_suffix = split_res
                system_blocks.append({
                    "type": "text",
                    "text": stable_prefix,
                    "cache_control": {"type": "ephemeral"},
                })
                if dynamic_suffix:
                    system_blocks.append({"type": "text", "text": dynamic_suffix})
            else:
                system_blocks.append({
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                })

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_blocks:
            payload["system"] = system_blocks

        async with httpx.AsyncClient(transport=self.transport, timeout=120.0) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content_blocks = data.get("content", [])
        final_text = ""
        reasoning_text = ""

        for b in content_blocks:
            b_type = b.get("type")
            if b_type == "text":
                final_text += b.get("text", "")
            elif b_type == "thinking":
                reasoning_text += b.get("thinking", "")

        usage = data.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        cached_tokens = usage.get("cache_read_input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        return {
            "content": final_text,
            "reasoning": reasoning_text,
            "prompt_tokens": prompt_tokens,
            "cached_prompt_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "provider": "anthropic",
        }
