"""
Auth Manager: Stealth Telegram PIN & Zero-Trust Channel Pairing.
Mengamankan akses Founder via DM Telegram dan platform perpesanan terdesentralisasi.
"""

from datetime import datetime, timezone
import secrets
from typing import Optional
import aiosqlite

from app.core.config import settings
from app.core.logger import logger


def validate_telegram_pin(input_pin: str) -> bool:
    """Memverifikasi PIN rahasia Founder via timing-attack resistant comparison."""
    if not input_pin:
        return False
    return secrets.compare_digest(input_pin.strip(), settings.TELEGRAM_STEALTH_PIN.strip())


async def generate_pairing_code(
    conn: aiosqlite.Connection,
    platform: str,
    external_user_id: str,
) -> str:
    """Menghasilkan kode pairing 6-digit untuk otorisasi perangkat/pengguna baru."""
    code = f"{secrets.randbelow(900000) + 100000}"
    pair_id = f"pair_{secrets.token_hex(6)}"

    await conn.execute(
        """
        INSERT INTO channel_pairings (id, channel_platform, external_user_id, pairing_code, is_approved)
        VALUES (?, ?, ?, ?, 0)
        ON CONFLICT(channel_platform, external_user_id) DO UPDATE SET
            pairing_code = excluded.pairing_code,
            is_approved = 0,
            approved_at = NULL;
        """,
        (pair_id, platform.lower(), str(external_user_id), code),
    )
    await conn.commit()
    logger.info(f"Kode pairing baru dihasilkan untuk platform [{platform}] user [{external_user_id}].")
    return code


async def approve_pairing_code(
    conn: aiosqlite.Connection,
    platform: str,
    external_user_id: str,
    pairing_code: str,
) -> bool:
    """Memvalidasi dan menyetujui handshake pairing channel."""
    cur = await conn.execute(
        """
        SELECT id, pairing_code FROM channel_pairings
        WHERE channel_platform = ? AND external_user_id = ? AND is_approved = 0
        """,
        (platform.lower(), str(external_user_id)),
    )
    row = await cur.fetchone()
    if not row:
        return False

    if secrets.compare_digest(row["pairing_code"], pairing_code.strip()):
        now_str = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE channel_pairings SET is_approved = 1, approved_at = ? WHERE id = ?",
            (now_str, row["id"]),
        )
        await conn.commit()
        logger.info(f"Channel pairing berhasil disetujui: [{platform}] [{external_user_id}].")
        return True
    return False


async def is_channel_approved(
    conn: aiosqlite.Connection,
    platform: str,
    external_user_id: str,
) -> bool:
    """Mengecek apakah pengguna channel telah diotorisasi."""
    cur = await conn.execute(
        "SELECT is_approved FROM channel_pairings WHERE channel_platform = ? AND external_user_id = ?",
        (platform.lower(), str(external_user_id)),
    )
    row = await cur.fetchone()
    return bool(row and row["is_approved"] == 1)
