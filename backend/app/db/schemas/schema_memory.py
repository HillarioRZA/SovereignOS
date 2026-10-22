"""
Schema DDL: Memory, Dreaming, Skills FTS5, & MCP Servers.
"""

DDL_CORPORATE_WISDOM = """
CREATE TABLE IF NOT EXISTS corporate_wisdom (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    embedding_blob BLOB NOT NULL,
    loss_protection_locked INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_MEMORY_DREAM_JOURNAL = """
CREATE TABLE IF NOT EXISTS memory_dream_journal (
    id TEXT PRIMARY KEY,
    sleep_stage TEXT NOT NULL,
    source_session_ids_json TEXT NOT NULL,
    synthesized_narrative TEXT NOT NULL,
    contradictions_resolved_json TEXT NOT NULL DEFAULT '[]',
    prior_entry_loss_fraction REAL NOT NULL DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_SKILLS = """
CREATE TABLE IF NOT EXISTS corporate_skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    skill_markdown TEXT NOT NULL,
    is_auto_generated INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER NOT NULL DEFAULT 0,
    patch_count INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_SKILLS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS corporate_skills_fts USING fts5(
    name, category, skill_markdown, content='corporate_skills', content_rowid='rowid',
    tokenize='unicode61'
);
"""

DDL_CORPORATE_CUSTOM_TOOLS = """
CREATE TABLE IF NOT EXISTS corporate_custom_tools (
    id TEXT PRIMARY KEY,
    tool_id TEXT NOT NULL UNIQUE REFERENCES tool_permissions_registry(tool_id),
    author_role_id TEXT NOT NULL,
    python_source_code TEXT NOT NULL,
    is_approved INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_MCP_SERVERS = """
CREATE TABLE IF NOT EXISTS corporate_mcp_servers (
    id TEXT PRIMARY KEY,
    server_name TEXT NOT NULL UNIQUE,
    transport_type TEXT NOT NULL,
    command_or_url TEXT NOT NULL,
    env_vars_encrypted TEXT,
    tools_manifest_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1
);
"""

MEMORY_DDL_LIST = [
    DDL_CORPORATE_WISDOM,
    DDL_MEMORY_DREAM_JOURNAL,
    DDL_CORPORATE_SKILLS,
    DDL_CORPORATE_SKILLS_FTS,
    DDL_CORPORATE_CUSTOM_TOOLS,
    DDL_CORPORATE_MCP_SERVERS,
]
