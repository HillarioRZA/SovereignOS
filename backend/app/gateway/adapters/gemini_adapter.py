"""
Google Gemini Native REST Adapter (Full-Native via HTTPX).
Mendukung Gemini 2.0/2.5 Flash & Pro tanpa library google-genai.
"""

from typing import Any, Dict, List, Optional
import httpx

from app.core.logger import logger
from app.gateway.adapters.base_adapter import BaseLLMAdapter
from app.gateway.tool_call_repair import extract_reasoning_and_content


class GeminiAdapter(BaseLLMAdapter):
    """Adapter resmi REST untuk Google Gemini API generateContent."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.transport = transport

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "gemini-2.5-flash",
        api_key: str = "",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
        thinking_level: str = "medium",
    ) -> Dict[str, Any]:
        endpoint = f"{base_url.rstrip('/')}/models/{model}:generateContent"
        params = {"key": api_key} if api_key else {}
        headers = {"Content-Type": "application/json"}

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        if system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": system_prompt}]
            }

        async with httpx.AsyncClient(transport=self.transport, timeout=120.0) as client:
            resp = await client.post(endpoint, params=params, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Respons kosong dari Gemini: {data}")

        parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(p.get("text", "") for p in parts)

        reasoning = ""
        final_content = raw_text
        if "<think>" in raw_text:
            reasoning, final_content = extract_reasoning_and_content(raw_text)

        usage = data.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        cached_tokens = usage.get("cachedContentTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return {
            "content": final_content,
            "reasoning": reasoning,
            "prompt_tokens": prompt_tokens,
            "cached_prompt_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "provider": "gemini",
        }
