"""
Phase 9: Context Compaction & Anti-Infinite Loop Circuit Breaker.
Menegakkan Invarian Suci 10:
- Batasi perulangan tanpa artefak maksimal 3 putaran (MAX_CONSECUTIVE_TURNS = 3).
- Two-tier context compaction: Upper Static Prefix tetap utuh, observasi lama dipangkas.
"""

from typing import Any, Dict, List, Tuple
import aiosqlite

from app.core.logger import logger


def compact_turn_history(
    messages: List[Dict[str, Any]],
    max_history_chars: int = 12000,
) -> List[Dict[str, Any]]:
    """Memangkas riwayat turn tanpa mengorbankan instruksi utama.
    
    Observasi perkakas lama diringkas agar tetap berada dalam jendela konteks efisien.
    """
    total_len = sum(len(str(m.get("content", ""))) for m in messages)
    if total_len <= max_history_chars:
        return messages

    logger.info(f"[ContextCompaction] Konteks ({total_len} karakter) melebihi batas. Melakukan kompresi...")
    compacted: List[Dict[str, Any]] = []

    # Pertahankan 2 pesan paling awal dan 3 pesan terbaru
    if len(messages) > 5:
        head = messages[:2]
        middle = messages[2:-3]
        tail = messages[-3:]

        compacted.extend(head)
        # Ringkas bagian tengah
        summary_text = f"[RINGKASAN_HISTORI]: {len(middle)} giliran sebelumnya diringkas."
        compacted.append({"role": "system", "content": summary_text})
        compacted.extend(tail)
    else:
        compacted = messages

    return compacted


def check_turn_loop_circuit_breaker(
    consecutive_empty_turns: int,
    max_allowed: int = 3,
) -> Tuple[bool, str]:
    """Mengevaluasi apakah agen terjebak dalam putaran percakapan tanpa menghasilkan artefak baru."""
    if consecutive_empty_turns >= max_allowed:
        msg = f"Loop terdeteksi: {consecutive_empty_turns} putaran berturut-turut tanpa menghasilkan artefak baru."
        logger.error(f"[CircuitBreaker] {msg} Status tiket dibekukan menjadi BLOCKED_LOOP_DETECTED.")
        return True, msg
    return False, ""
