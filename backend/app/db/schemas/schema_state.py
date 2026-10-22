"""
Schema DDL: State, Lease, Vault, & Konfigurasi Sistem.
"""

DDL_STATE_LEASES = """
CREATE TABLE IF NOT EXISTS state_leases (
    lease_key TEXT PRIMARY KEY,
    owner_process_id TEXT NOT NULL,
    generation_id INTEGER NOT NULL DEFAULT 1,
    wal_inode TEXT,
    acquired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL
);
"""

DDL_QUARANTINE_STORE = """
CREATE TABLE IF NOT EXISTS quarantine_store (
    id TEXT PRIMARY KEY,
    source_table TEXT NOT NULL,
    corrupted_payload_json TEXT NOT NULL,
    error_reason TEXT NOT NULL,
    quarantined_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_VAULT_SECRETS = """
CREATE TABLE IF NOT EXISTS vault_secrets (
    secret_key TEXT NOT NULL,
    profile_scope TEXT NOT NULL DEFAULT 'default',
    ciphertext_aes_gcm TEXT NOT NULL,
    nonce TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (secret_key, profile_scope)
);
"""

DDL_SYSTEM_SETTINGS = """
CREATE TABLE IF NOT EXISTS system_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CHANNEL_PAIRINGS = """
CREATE TABLE IF NOT EXISTS channel_pairings (
    id TEXT PRIMARY KEY,
    channel_platform TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    pairing_code TEXT NOT NULL,
    is_approved INTEGER NOT NULL DEFAULT 0,
    approved_at DATETIME,
    UNIQUE(channel_platform, external_user_id)
);
"""

STATE_DDL_LIST = [
    DDL_STATE_LEASES,
    DDL_QUARANTINE_STORE,
    DDL_VAULT_SECRETS,
    DDL_SYSTEM_SETTINGS,
    DDL_CHANNEL_PAIRINGS,
]
