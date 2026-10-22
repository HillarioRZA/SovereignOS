"""
Unit Test Suite untuk Prompt Cache Boundary & Tool Schema Determinism (OpenClaw style).
Menguji stabilitas byte, pemisahan cache boundary, dan pengurutan alfabetis perkakas.
"""

import pytest
from app.gateway.cache_boundary import (
    SOVEREIGN_CACHE_BOUNDARY,
    compute_sha256_digest,
    sort_tools_alphabetically,
    split_system_prompt_cache_boundary,
    ensure_system_prompt_cache_boundary,
    assemble_cached_system_prompt,
)


def test_sha256_digest_determinism():
    """Memverifikasi bahwa digest SHA-256 identik untuk konten yang sama."""
    d1 = compute_sha256_digest("Hello Sovereign OS")
    d2 = compute_sha256_digest("Hello Sovereign OS")
    d3 = compute_sha256_digest("Different text")
    assert d1 == d2
    assert d1 != d3
    assert len(d1) == 64


def test_sort_tools_alphabetically():
    """Memverifikasi bahwa pengurutan perkakas selalu alfabetis deterministik."""
    tools = [
        {"name": "write_file", "parameters": {"path": "str"}},
        {"name": "read_file", "parameters": {"path": "str"}},
        {"name": "execute_code", "parameters": {"code": "str"}},
    ]
    sorted_tools, digest = sort_tools_alphabetically(tools)
    names = [t["name"] for t in sorted_tools]
    assert names == ["execute_code", "read_file", "write_file"]
    assert len(digest) == 64

    # Urutan input acak harus tetap menghasilkan digest yang persis sama
    tools_reversed = list(reversed(tools))
    _, digest_rev = sort_tools_alphabetically(tools_reversed)
    assert digest == digest_rev


def test_split_and_ensure_cache_boundary():
    """Menguji pemisahan boundary cache dan penambahan boundary jika belum ada."""
    sample = f"Upper Static Prefix{SOVEREIGN_CACHE_BOUNDARY}Lower Volatile Context"
    split_res = split_system_prompt_cache_boundary(sample)
    assert split_res is not None
    prefix, suffix = split_res
    assert prefix == "Upper Static Prefix"
    assert suffix == "Lower Volatile Context"

    # Test no boundary
    assert split_system_prompt_cache_boundary("Text without boundary") is None

    # Test ensure boundary
    ensured = ensure_system_prompt_cache_boundary("Static prompt only")
    assert SOVEREIGN_CACHE_BOUNDARY in ensured
    assert ensured.startswith("Static prompt only")


def test_assemble_cached_system_prompt():
    """Menguji perakitan prompt 3-Layer dengan Upper Prefix dan Lower Context."""
    persona = "You are a software architect."
    sop = "Always write clean code and test thoroughly."
    tools = [{"name": "builtin:read_file", "description": "Reads a file"}]
    dynamic_ctx = "TICKET #101: Build Auth API"

    full_prompt, sys_digest, tool_digest = assemble_cached_system_prompt(
        persona_prompt=persona,
        sop_template=sop,
        sorted_tools=tools,
        dynamic_context=dynamic_ctx,
    )

    assert SOVEREIGN_CACHE_BOUNDARY in full_prompt
    assert "LAYER 1: IMMUTABLE SOUL" in full_prompt
    assert "LAYER 2: STATIC OPERATIONAL SOP" in full_prompt
    assert "LAYER 3: DYNAMIC TASK CONTEXT" in full_prompt
    assert "TICKET #101" in full_prompt

    # Uji bahwa sys_digest hanya dipengaruhi oleh static prefix
    full_prompt_2, sys_digest_2, _ = assemble_cached_system_prompt(
        persona_prompt=persona,
        sop_template=sop,
        sorted_tools=tools,
        dynamic_context="DIFFERENT TICKET #999",
    )
    # Digest static prefix HARUS IDENTIK meskipun tiket dinamis berubah! (Prompt Caching Berhasil)
    assert sys_digest == sys_digest_2
