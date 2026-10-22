"""
Byte-Stable System Prompt Cache Boundary & Section Digest Engine.
Terinspirasi dari OpenClaw & Hermes untuk efisiensi prompt caching (Anthropic, DeepSeek, Gemini).
Menegakkan Invarian Suci 3: Pemisahan tegas Upper Static Prefix dan Lower Volatile Context.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

SOVEREIGN_CACHE_BOUNDARY = "\n<!-- SOVEREIGN_CACHE_BOUNDARY -->\n"


def compute_sha256_digest(content: str) -> str:
    """Menghitung hash SHA-256 heksadesimal untuk string atau payload teks."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def sort_tools_alphabetically(
    tools: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], str]:
    """Mengurutkan definisi skema perkakas secara alfabetis berdasarkan nama perkakas.
    
    Menjamin stabilitas urutan byte pada skema perkakas yang dikirim ke LLM.
    Mengembalikan:
        Tuple (sorted_tools, tool_schema_digest_sha256).
    """
    if not tools:
        return [], hashlib.sha256(b"empty_tools").hexdigest()

    # Urutkan berdasarkan kunci 'name' atau 'tool_id'
    sorted_tools = sorted(
        tools,
        key=lambda t: t.get("name", t.get("tool_id", "")).lower()
    )

    # Serialisasi deterministik untuk digest
    normalized_schemas = [
        f"{t.get('name', t.get('tool_id'))}:{json.dumps(t.get('parameters', {}), sort_keys=True)}"
        for t in sorted_tools
    ]
    digest = hashlib.sha256(";".join(normalized_schemas).encode("utf-8")).hexdigest()
    return sorted_tools, digest


def split_system_prompt_cache_boundary(
    text: str
) -> Optional[Tuple[str, str]]:
    """Memisahkan system prompt pada batas SOVEREIGN_CACHE_BOUNDARY.
    
    Mengembalikan:
        Tuple (stable_prefix, dynamic_suffix) jika boundary ditemukan,
        atau None jika boundary tidak ada.
    """
    idx = text.find(SOVEREIGN_CACHE_BOUNDARY)
    if idx == -1:
        return None
    stable_prefix = text[:idx].rstrip()
    dynamic_suffix = text[idx + len(SOVEREIGN_CACHE_BOUNDARY):].lstrip()
    return stable_prefix, dynamic_suffix


def ensure_system_prompt_cache_boundary(system_prompt: str) -> str:
    """Memastikan system prompt memiliki tanda SOVEREIGN_CACHE_BOUNDARY di akhir jika belum ada."""
    clean_prompt = system_prompt.strip()
    if not clean_prompt:
        return clean_prompt
    if SOVEREIGN_CACHE_BOUNDARY in clean_prompt:
        return clean_prompt
    return f"{clean_prompt}{SOVEREIGN_CACHE_BOUNDARY}"


def assemble_cached_system_prompt(
    persona_prompt: str,
    sop_template: str,
    sorted_tools: List[Dict[str, Any]],
    dynamic_context: str = "",
) -> Tuple[str, str, str]:
    """Merakit system prompt 3-Layer dengan batas byte-stable prompt cache.
    
    UPPER SECTION (100% Byte-Stable & Di-cache):
      - Layer 1: Immutable Soul (persona_prompt)
      - Layer 2: Static Operational SOP (sop_template)
      - Sorted Tool Schemas (skema perkakas diurutkan alfabetis)
    
    BOUNDARY:
      <!-- SOVEREIGN_CACHE_BOUNDARY -->
    
    LOWER SECTION (Volatile Dynamic Turn Context):
      - Layer 3: Task context, @mention instruction, blackboard, container diagnostics.
    
    Mengembalikan:
      Tuple (full_assembled_prompt, system_prompt_digest, tool_schema_digest).
    """
    # 1. Hitung tool digest
    _, tool_digest = sort_tools_alphabetically(sorted_tools)

    # 2. Bangun Upper Static Prefix
    upper_parts = [
        "=== LAYER 1: IMMUTABLE SOUL & PERSONA ===",
        persona_prompt.strip(),
        "\n=== LAYER 2: STATIC OPERATIONAL SOP & RULES ===",
        sop_template.strip(),
    ]

    if sorted_tools:
        tool_descriptions = []
        for t in sorted_tools:
            t_name = t.get("name", t.get("tool_id", ""))
            t_desc = t.get("description", "")
            tool_descriptions.append(f"- `{t_name}`: {t_desc}")
        upper_parts.append("\n=== AUTHORIZED TOOLS (ORDER DETERMINISTIC) ===")
        upper_parts.append("\n".join(tool_descriptions))

    stable_prefix = "\n\n".join(upper_parts).strip()
    system_prompt_digest = compute_sha256_digest(stable_prefix)

    # 3. Rakit dengan Lower Dynamic Section
    if dynamic_context.strip():
        lower_section = f"=== LAYER 3: DYNAMIC TASK CONTEXT & INSTRUCTIONS ===\n{dynamic_context.strip()}"
        full_prompt = f"{stable_prefix}{SOVEREIGN_CACHE_BOUNDARY}{lower_section}"
    else:
        full_prompt = ensure_system_prompt_cache_boundary(stable_prefix)

    return full_prompt, system_prompt_digest, tool_digest
