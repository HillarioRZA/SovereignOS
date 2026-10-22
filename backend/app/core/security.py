"""
AES-256-GCM Vault Cryptography & Security Utilities.
Menjamin penyimpanan kredensial multi-provider terenkripsi dengan nonces unik 96-bit.
"""

import base64
import hashlib
import os
from typing import Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _derive_key(master_key: str) -> bytes:
    """Menghasilkan kunci 32-byte (256-bit) dari master key menggunakan SHA-256."""
    return hashlib.sha256(master_key.encode("utf-8")).digest()


def encrypt_secret(plaintext: str, custom_master_key: str = "") -> Tuple[str, str]:
    """Mengenkripsi teks rahasia menggunakan AES-256-GCM.
    
    Returns:
        Tuple (ciphertext_base64, nonce_base64).
    """
    key = _derive_key(custom_master_key or settings.VAULT_MASTER_KEY)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce standar GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_secret(ciphertext_b64: str, nonce_b64: str, custom_master_key: str = "") -> str:
    """Mendekripsi ciphertext AES-256-GCM kembali ke plaintext string."""
    key = _derive_key(custom_master_key or settings.VAULT_MASTER_KEY)
    aesgcm = AESGCM(key)
    ciphertext = base64.b64decode(ciphertext_b64.encode("ascii"))
    nonce = base64.b64decode(nonce_b64.encode("ascii"))
    
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")
