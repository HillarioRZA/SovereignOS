"""
Unit Test Suite untuk SovereignModelRouter, UpstreamChannel, dan ToolCallRepair.
"""

import json
import pytest
import httpx

from app.gateway.model_router import UpstreamChannel, SovereignModelRouter
from app.gateway.tool_call_repair import (
    parse_and_repair_json,
    extract_tool_calls,
    extract_reasoning_and_content,
)


def test_upstream_channel_cooldown():
    """Menguji aktivasi cooldown pada kanal hulu setelah 429."""
    channel = UpstreamChannel("anthropic", "claude-3-7-sonnet", rpm_limit=10)
    assert channel.is_healthy() is True

    # Set cooldown 60 detik
    channel.set_cooldown(60)
    assert channel.is_healthy() is False


def test_cost_calculation():
    """Menguji kalkulasi biaya token Cost-IQ."""
    # 1000 prompt, 500 cached, 200 completion untuk claude-3-7-sonnet
    cost_claude = SovereignModelRouter.calculate_cost_usd(
        "claude-3-7-sonnet",
        prompt_tokens=1000,
        cached_prompt_tokens=500,
        completion_tokens=200,
    )
    assert cost_claude > 0.0

    # DeepSeek cost
    cost_deepseek = SovereignModelRouter.calculate_cost_usd(
        "deepseek-chat",
        prompt_tokens=1000,
        cached_prompt_tokens=500,
        completion_tokens=200,
    )
    assert cost_deepseek < cost_claude  # DeepSeek jauh lebih hemat


def test_tool_call_repair_and_extraction():
    """Menguji parsing dan perbaikan sintaks JSON perkakas."""
    # 1. Format blok markdown ```json ... ``` dengan trailing comma
    broken_md = """
    Berikut perkakas yang saya panggil:
    ```json
    {
        "tool": "builtin:write_file",
        "parameters": {
            "file_path": "main.py",
            "content": "print('hello')",
        }
    }
    ```
    """
    calls = extract_tool_calls(broken_md)
    assert len(calls) == 1
    assert calls[0]["tool_id"] == "builtin:write_file"
    assert calls[0]["parameters"]["file_path"] == "main.py"

    # 2. Format inline json dengan tanda kurung terpotong
    incomplete_json = '{"name": "builtin:read_file", "arguments": {"file_path": "test.txt"'
    repaired = parse_and_repair_json(incomplete_json)
    assert repaired is not None
    assert repaired.get("name") == "builtin:read_file"


def test_extract_reasoning_and_content():
    """Menguji ekstraksi pemikiran agen di dalam tag <think>...</think>."""
    raw = "<think>Saya perlu membaca file config terlebih dahulu.</think>Saya akan membaca berkas config."
    reasoning, content = extract_reasoning_and_content(raw)
    assert reasoning == "Saya perlu membaca file config terlebih dahulu."
    assert content == "Saya akan membaca berkas config."


@pytest.mark.asyncio
async def test_model_router_with_mock_transport():
    """Menguji eksekusi router dengan mock HTTP transport."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"tool": "builtin:read_file", "parameters": {"file_path": "README.md"}}',
                            "reasoning_content": "Memeriksa file README",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "prompt_tokens_details": {"cached_tokens": 40},
                    "completion_tokens": 50,
                },
            },
        )

    mock_transport = httpx.MockTransport(mock_handler)
    router = SovereignModelRouter(transport=mock_transport)

    result = await router.execute_routed_completion(
        prompt="Baca file README",
        primary_provider="openai_compatible",
        primary_model="deepseek-chat",
    )

    assert "builtin:read_file" in result["content"]
    assert result["reasoning"] == "Memeriksa file README"
    assert result["prompt_tokens"] == 100
    assert result["cached_prompt_tokens"] == 40
    assert result["cost_usd"] > 0.0
