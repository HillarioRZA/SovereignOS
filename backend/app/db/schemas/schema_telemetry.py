"""
Schema DDL: Telemetry, 4-Stream Messages, FTS5 Search, FinOps Ledger, & Sentinel Audit Logs.
"""

DDL_CORPORATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS corporate_messages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    stream_category TEXT NOT NULL,
    sender_role_id TEXT,
    scoped_recipient_role_id TEXT,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_MESSAGES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, project_id UNINDEXED, sender_role_id UNINDEXED
);
"""

DDL_CORPORATE_TOKEN_LEDGER = """
CREATE TABLE IF NOT EXISTS corporate_token_ledger (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    ticket_id TEXT,
    role_id TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    system_prompt_digest TEXT NOT NULL,
    tool_schema_digest TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    cached_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_SENTINEL_AUDIT_LOGS = """
CREATE TABLE IF NOT EXISTS sentinel_audit_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    ticket_id TEXT,
    role_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    tier_evaluated INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    repair_feedback TEXT,
    latency_ms REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_VENTURE_FINANCIAL_LEDGER = """
CREATE TABLE IF NOT EXISTS venture_financial_ledger (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    is_recurring INTEGER NOT NULL DEFAULT 0,
    period_month TEXT NOT NULL,
    notes TEXT,
    recorded_by_role_id TEXT NOT NULL REFERENCES corporate_roles(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

INDEX_MESSAGES_STREAM = """
CREATE INDEX IF NOT EXISTS idx_msgs_proj_stream ON corporate_messages(project_id, stream_category);
"""

INDEX_MESSAGES_SCOPED = """
CREATE INDEX IF NOT EXISTS idx_msgs_scoped ON corporate_messages(scoped_recipient_role_id);
"""

INDEX_VENTURE_FINANCIAL_LEDGER = """
CREATE INDEX IF NOT EXISTS idx_vfl_proj_period ON venture_financial_ledger(project_id, period_month);
"""

TELEMETRY_DDL_LIST = [
    DDL_CORPORATE_MESSAGES,
    DDL_MESSAGES_FTS,
    DDL_CORPORATE_TOKEN_LEDGER,
    DDL_SENTINEL_AUDIT_LOGS,
    DDL_VENTURE_FINANCIAL_LEDGER,
    INDEX_MESSAGES_STREAM,
    INDEX_MESSAGES_SCOPED,
    INDEX_VENTURE_FINANCIAL_LEDGER,
]
