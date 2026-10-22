"""
OpenAI-Compatible LLM Adapter (Full-Native via HTTPX).
Mendukung DeepSeek, OpenAI, Groq, Mistral, Ollama, OpenRouter, dan Nous Portal.
"""

from typing import Any, Dict, List, Optional
import httpx

from app.core.logger import logger
from app.gateway.adapters.base_adapter import BaseLLMAdapter
from app.gateway.tool_call_repair import extract_reasoning_and_content


class OpenAICompatibleAdapter(BaseLLMAdapter):
    """Adapter untuk semua endpoint standar /chat/completions."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.transport = transport

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "deepseek-chat",
        api_key: str = "",
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
        thinking_level: str = "medium",
    ) -> Dict[str, Any]:
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(transport=self.transport, timeout=120.0) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"Respons kosong dari penyedia model: {data}")

        choice = choices[0]
        msg = choice.get("message", {})
        raw_content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""

        # Jika reasoning belum ada di reasoning_content, ekstrak dari tag <think>
        if not reasoning and "<think>" in raw_content:
            extracted_think, clean_content = extract_reasoning_and_content(raw_content)
            reasoning = extracted_think
            raw_content = clean_content

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        prompt_details = usage.get("prompt_tokens_details", {})
        cached_tokens = prompt_details.get("cached_tokens", 0) if isinstance(prompt_details, dict) else 0
        completion_tokens = usage.get("completion_tokens", 0)

        return {
            "content": raw_content,
            "reasoning": reasoning,
            "prompt_tokens": prompt_tokens,
            "cached_prompt_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "model": model,
            "provider": "openai_compatible",
        }
