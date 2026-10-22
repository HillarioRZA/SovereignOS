"""
Unit Tests for AES-256-GCM Vault, Secret Scope, & Auth Manager.
"""

import gc
import os
import tempfile
import pytest

from app.core.security import encrypt_secret, decrypt_secret
from app.core.secret_scope import set_vault_secret, get_vault_secret, list_vault_keys, delete_vault_secret
from app.core.auth_manager import validate_telegram_pin, generate_pairing_code, approve_pairing_code, is_channel_approved
from app.db.session import get_db_connection
from app.db.schemas import execute_ddl_migrations


def _safe_remove(path: str) -> None:
    gc.collect()
    for p in [path, f"{path}-wal", f"{path}-shm"]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def test_aes_256_gcm_encryption_roundtrip():
    """Uji roundtrip enkripsi dan dekripsi AES-256-GCM beserta keunikan nonce."""
    secret = "sk-ant-api03-test-secret-key-12345"
    ct1, nonce1 = encrypt_secret(secret)
    ct2, nonce2 = encrypt_secret(secret)

    # Pastikan ciphertext dan nonce unik per enkripsi (probabilistik)
    assert ct1 != ct2
    assert nonce1 != nonce2

    # Dekripsi harus menghasilkan plaintext asli
    decrypted = decrypt_secret(ct1, nonce1)
    assert decrypted == secret


@pytest.mark.asyncio
async def test_vault_secret_scope_isolation():
    """Uji isolasi vault antar-profile tenant."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            await execute_ddl_migrations(conn)

            # Simpan key yang sama pada dua profile berbeda
            await set_vault_secret(conn, "OPENAI_API_KEY", "key_tenant_alpha", profile_scope="alpha")
            await set_vault_secret(conn, "OPENAI_API_KEY", "key_tenant_beta", profile_scope="beta")

            # Ambil kembali dan verifikasi isolasi
            val_alpha = await get_vault_secret(conn, "OPENAI_API_KEY", profile_scope="alpha")
            val_beta = await get_vault_secret(conn, "OPENAI_API_KEY", profile_scope="beta")

            assert val_alpha == "key_tenant_alpha"
            assert val_beta == "key_tenant_beta"

            keys_alpha = await list_vault_keys(conn, profile_scope="alpha")
            assert "OPENAI_API_KEY" in keys_alpha

            del_ok = await delete_vault_secret(conn, "OPENAI_API_KEY", profile_scope="alpha")
            assert del_ok is True
            assert await get_vault_secret(conn, "OPENAI_API_KEY", profile_scope="alpha") is None
    finally:
        _safe_remove(db_path)


@pytest.mark.asyncio
async def test_stealth_telegram_pin_and_channel_pairing():
    """Uji verifikasi PIN Telegram dan handshake zero-trust channel pairing."""
    # Uji PIN Telegram
    assert validate_telegram_pin("999888") is True
    assert validate_telegram_pin("wrong_pin") is False

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async with get_db_connection(db_path) as conn:
            await execute_ddl_migrations(conn)

            # Generate kode pairing untuk pengguna Telegram
            code = await generate_pairing_code(conn, "telegram", "user_12345")
            assert len(code) == 6

            # Sebelum diapprove, is_channel_approved harus False
            assert await is_channel_approved(conn, "telegram", "user_12345") is False

            # Approve dengan kode yang salah -> False
            assert await approve_pairing_code(conn, "telegram", "user_12345", "000000") is False

            # Approve dengan kode yang benar -> True
            assert await approve_pairing_code(conn, "telegram", "user_12345", code) is True

            # Sekarang harus True
            assert await is_channel_approved(conn, "telegram", "user_12345") is True
    finally:
        _safe_remove(db_path)
