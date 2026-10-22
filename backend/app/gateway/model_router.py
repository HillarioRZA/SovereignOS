"""
Sovereign Model Router (Multi-Provider BYOK Gateway).
Menyediakan orkestrasi 30+ provider, RPM/TPM pre-flight throttling, auto-cooldown 429,
Cost-IQ token calculation, dan failover cascade per peran.
"""

import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import aiosqlite
import httpx

from app.core.config import settings
from app.core.logger import logger
from app.gateway.adapters.base_adapter import BaseLLMAdapter
from app.gateway.adapters.openai_compatible import OpenAICompatibleAdapter
from app.gateway.adapters.anthropic_adapter import AnthropicAdapter
from app.gateway.adapters.gemini_adapter import GeminiAdapter


class UpstreamChannel:
    """Manajer kanal provider hulu dengan kontrol kuota RPM/TPM dan auto-cooldown."""

    def __init__(self, provider: str, model: str, rpm_limit: int = 30, tpm_limit: int = 60000) -> None:
        self.provider = provider.lower()
        self.model = model
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.cooldown_until: Optional[float] = None
        self.request_timestamps: List[float] = []
        self.token_window: List[Tuple[float, int]] = []

    def is_healthy(self) -> bool:
        if self.cooldown_until:
            if time.time() < self.cooldown_until:
                return False
            self.cooldown_until = None
        return True

    def set_cooldown(self, seconds: int = 60) -> None:
        self.cooldown_until = time.time() + seconds
        logger.warning(f"Kanal [{self.provider}/{self.model}] di-cooldown selama {seconds} detik.")

    async def throttle_if_needed(self, estimated_tokens: int = 2000) -> None:
        now = time.time()
        self.request_timestamps = [t for t in self.request_timestamps if now - t < 60]
        self.token_window = [(t, tok) for t, tok in self.token_window if now - t < 60]
        
        current_rpm = len(self.request_timestamps)
        current_tpm = sum(tok for _, tok in self.token_window)

        if current_rpm >= self.rpm_limit or (current_tpm + estimated_tokens) >= self.tpm_limit:
            logger.info(f"Throttling aktif pada [{self.provider}]: RPM {current_rpm}/{self.rpm_limit}. Tunggu 1.5s.")
            await asyncio.sleep(1.5)

        self.request_timestamps.append(time.time())
        self.token_window.append((time.time(), estimated_tokens))


class SovereignModelRouter:
    """Router terpadu tingkat enterprise untuk routing model LLM multi-kanal otonom."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.transport = transport
        self.openai_compat = OpenAICompatibleAdapter(transport=transport)
        self.anthropic = AnthropicAdapter(transport=transport)
        self.gemini = GeminiAdapter(transport=transport)
        self.channels: Dict[str, UpstreamChannel] = {}

    def _get_channel(self, provider: str, model: str) -> UpstreamChannel:
        key = f"{provider.lower()}:{model}"
        if key not in self.channels:
            rpm = 15 if "free" in model.lower() else 40
            tpm = 30000 if "free" in model.lower() else 100000
            self.channels[key] = UpstreamChannel(provider, model, rpm_limit=rpm, tpm_limit=tpm)
        return self.channels[key]

    def _resolve_adapter(self, provider: str) -> BaseLLMAdapter:
        p = provider.lower()
        if p == "anthropic":
            return self.anthropic
        elif p == "gemini":
            return self.gemini
        else:
            return self.openai_compat

    def _resolve_credentials(self, provider: str) -> Tuple[str, str]:
        p = provider.lower()
        if p == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY", ""), os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
        elif p == "gemini":
            return os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        elif p == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY", ""), os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        elif p == "openrouter":
            return os.getenv("OPENROUTER_API_KEY", ""), os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        elif p == "ollama":
            return "", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        elif p in ("openai_compatible", "custom"):
            api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
            base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.tokenomixai.com/v1")
            return api_key, base_url
        else:
            return os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    @staticmethod
    def calculate_cost_usd(
        model: str,
        prompt_tokens: int,
        cached_prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Menghitung perkiraan biaya token berdasarkan profil harga pasar umum."""
        m = model.lower()
        if "claude-3-7-sonnet" in m or "claude-3-5-sonnet" in m:
            cost = (prompt_tokens * 3.0 / 1e6) + (cached_prompt_tokens * 0.3 / 1e6) + (completion_tokens * 15.0 / 1e6)
        elif "gpt-4o" in m:
            cost = (prompt_tokens * 2.5 / 1e6) + (cached_prompt_tokens * 1.25 / 1e6) + (completion_tokens * 10.0 / 1e6)
        elif "deepseek" in m:
            cost = (prompt_tokens * 0.27 / 1e6) + (cached_prompt_tokens * 0.07 / 1e6) + (completion_tokens * 1.1 / 1e6)
        else:
            cost = (prompt_tokens * 0.15 / 1e6) + (completion_tokens * 0.6 / 1e6)
        return round(cost, 6)

    async def execute_routed_completion(
        self,
        prompt: str,
        system_prompt: str = "",
        primary_provider: str = "anthropic",
        primary_model: str = "claude-3-7-sonnet",
        fallback_models: Optional[List[str]] = None,
        temperature: float = 0.2,
        thinking_level: str = "medium",
    ) -> Dict[str, Any]:
        """Menjalankan panggilan completion dengan failover cascade otomatis ke model cadangan."""
        candidates: List[Tuple[str, str]] = [(primary_provider, primary_model)]
        
        if fallback_models:
            for fb in fallback_models:
                if "/" in fb:
                    prov, mdl = fb.split("/", 1)
                else:
                    prov, mdl = "openai_compatible", fb
                candidates.append((prov, mdl))

        last_error: Optional[Exception] = None

        for prov, mdl in candidates:
            channel = self._get_channel(prov, mdl)
            if not channel.is_healthy():
                logger.info(f"Kanal [{prov}/{mdl}] sedang dalam masa cooldown. Melewati ke kandidat berikutnya.")
                continue

            await channel.throttle_if_needed(estimated_tokens=len(prompt) // 4)
            adapter = self._resolve_adapter(prov)
            api_key, base_url = self._resolve_credentials(prov)

            try:
                logger.info(f"[ModelRouter] Memanggil [{prov}] dengan model [{mdl}]...")
                result = await adapter.complete(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=mdl,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=temperature,
                    thinking_level=thinking_level,
                )
                
                # Hitung biaya
                cost = self.calculate_cost_usd(
                    mdl,
                    result.get("prompt_tokens", 0),
                    result.get("cached_prompt_tokens", 0),
                    result.get("completion_tokens", 0),
                )
                result["cost_usd"] = cost
                return result

            except httpx.HTTPStatusError as http_err:
                status_code = http_err.response.status_code
                logger.warning(f"Kanal [{prov}/{mdl}] gagal dengan HTTP {status_code}: {http_err}")
                if status_code in (429, 503, 500):
                    channel.set_cooldown(60)
                last_error = http_err
            except (httpx.TimeoutException, httpx.RequestError) as net_err:
                logger.warning(f"Kanal [{prov}/{mdl}] mengalami timeout/network error: {net_err}")
                channel.set_cooldown(30)
                last_error = net_err
            except Exception as err:
                logger.warning(f"Kanal [{prov}/{mdl}] mengalami error tak terduga: {err}")
                last_error = err

        raise RuntimeError(f"Semua kanal model ({len(candidates)} kandidat) gagal dieksekusi. Error terakhir: {last_error}")
