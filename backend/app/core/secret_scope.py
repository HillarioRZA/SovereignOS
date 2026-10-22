"""
Scoped Secret Vault Store.
Mengelola isolasi kredensial per profile/tenant di tabel vault_secrets.
"""

from datetime import datetime, timezone
from typing import List, Optional
import aiosqlite

from app.core.security import encrypt_secret, decrypt_secret
from app.core.logger import logger


async def set_vault_secret(
    conn: aiosqlite.Connection,
    secret_key: str,
    plaintext: str,
    profile_scope: str = "default",
) -> None:
    """Mengenkripsi dan menyimpan kredensial ke dalam vault_secrets."""
    ciphertext_b64, nonce_b64 = encrypt_secret(plaintext)
    now_str = datetime.now(timezone.utc).isoformat()

    await conn.execute(
        """
        INSERT INTO vault_secrets (secret_key, profile_scope, ciphertext_aes_gcm, nonce, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(secret_key, profile_scope) DO UPDATE SET
            ciphertext_aes_gcm = excluded.ciphertext_aes_gcm,
            nonce = excluded.nonce,
            updated_at = excluded.updated_at;
        """,
        (secret_key, profile_scope, ciphertext_b64, nonce_b64, now_str),
    )
    await conn.commit()
    logger.info(f"Secret [{secret_key}] (scope: {profile_scope}) berhasil disimpan di vault.")


async def get_vault_secret(
    conn: aiosqlite.Connection,
    secret_key: str,
    profile_scope: str = "default",
) -> Optional[str]:
    """Mengambil dan mendekripsi kredensial dari vault_secrets secara aman in-memory."""
    cur = await conn.execute(
        "SELECT ciphertext_aes_gcm, nonce FROM vault_secrets WHERE secret_key = ? AND profile_scope = ?",
        (secret_key, profile_scope),
    )
    row = await cur.fetchone()
    if not row:
        return None
    try:
        return decrypt_secret(row["ciphertext_aes_gcm"], row["nonce"])
    except Exception as err:
        logger.error(f"Gagal mendekripsi secret [{secret_key}]: {err}")
        return None


async def list_vault_keys(
    conn: aiosqlite.Connection,
    profile_scope: str = "default",
) -> List[str]:
    """Mengambil daftar kunci kredensial tanpa membocorkan ciphertext."""
    cur = await conn.execute(
        "SELECT secret_key FROM vault_secrets WHERE profile_scope = ?",
        (profile_scope,),
    )
    rows = await cur.fetchall()
    return [r["secret_key"] for r in rows]


async def delete_vault_secret(
    conn: aiosqlite.Connection,
    secret_key: str,
    profile_scope: str = "default",
) -> bool:
    """Menghapus secret dari vault."""
    cur = await conn.execute(
        "DELETE FROM vault_secrets WHERE secret_key = ? AND profile_scope = ?",
        (secret_key, profile_scope),
    )
    await conn.commit()
    return cur.rowcount > 0
