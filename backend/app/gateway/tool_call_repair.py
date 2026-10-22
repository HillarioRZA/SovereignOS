"""
Tool Call Syntax & JSON Repair Engine.
Mem-parsing dan memperbaiki argumen JSON perkakas yang rusak atau terpotong tanda petik/markdown.
Terinspirasi dari OpenClaw & Hermes Tool Parser.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def _repair_common_json_errors(raw_json: str) -> str:
    """Melakukan perbaikan heuristik pada kesalahan umum sintaks JSON dari LLM."""
    s = raw_json.strip()

    # 1. Periksa tanda petik ganda yang belum tertutup
    if s.count('"') % 2 != 0:
        s += '"'
    
    # 2. Hapus trailing comma sebelum penutup kurung kurawal atau siku
    s = re.sub(r",\s*([\]}])", r"\1", s)
    
    # 3. Ganti single quote yang bertindak sebagai pembungkus kunci/nilai
    if "'" in s and '"' not in s:
        s = s.replace("'", '"')
        
    # 4. Seimbangkan tanda kurung penutup jika terpotong
    open_curly = s.count("{")
    close_curly = s.count("}")
    if open_curly > close_curly:
        s += "}" * (open_curly - close_curly)
        
    open_square = s.count("[")
    close_square = s.count("]")
    if open_square > close_square:
        s += "]" * (open_square - close_square)
        
    return s


def parse_and_repair_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """Mencoba mem-parsing JSON, dan jika gagal, melakukan perbaikan heuristik."""
    cleaned = raw_text.strip()
    if not cleaned:
        return None

    # Percobaan 1: Parsing langsung
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Percobaan 2: Ekstraksi dari blok kode markdown ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        snippet = match.group(1).strip()
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            repaired = _repair_common_json_errors(snippet)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

    # Percobaan 3: Ekstraksi kurung kurawal terluar pertama
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1:
        snippet = cleaned[start : end + 1] if (end != -1 and end > start) else cleaned[start:]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            repaired = _repair_common_json_errors(snippet)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

    return None


def extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    """Mengekstraksi satu atau beberapa pemanggilan perkakas dari respons LLM.
    
    Mendukung format:
    1. {"tool": "builtin:read_file", "parameters": {...}}
    2. {"name": "builtin:read_file", "arguments": {...}}
    3. {"tool_id": "builtin:read_file", "parameters": {...}}
    4. Blok ```json { ... } ```
    """
    results: List[Dict[str, Any]] = []

    # Cek format blok markdown JSON
    matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for m in matches:
        parsed = parse_and_repair_json(m)
        if isinstance(parsed, dict):
            tool_id = parsed.get("tool") or parsed.get("tool_id") or parsed.get("name")
            params = parsed.get("parameters") or parsed.get("arguments") or {}
            if tool_id:
                results.append({"tool_id": tool_id, "parameters": params})

    if results:
        return results

    # Cek format inline JSON
    parsed = parse_and_repair_json(text)
    if isinstance(parsed, dict):
        tool_id = parsed.get("tool") or parsed.get("tool_id") or parsed.get("name")
        params = parsed.get("parameters") or parsed.get("arguments") or {}
        if tool_id:
            results.append({"tool_id": tool_id, "parameters": params})

    return results


def extract_reasoning_and_content(raw_text: str) -> Tuple[str, str]:
    """Memisahkan pemikiran / reasoning tokens (misal di dalam tag <think>...</think>) dari konten akhir.
    
    Mengembalikan:
        Tuple (reasoning_text, final_content).
    """
    think_match = re.search(r"<think>(.*?)</think>", raw_text, re.DOTALL)
    if think_match:
        reasoning = think_match.group(1).strip()
        final_content = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
        return reasoning, final_content
    return "", raw_text.strip()
