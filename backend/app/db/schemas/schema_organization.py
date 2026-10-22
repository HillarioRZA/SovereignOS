"""
Schema DDL: Organization (16 Divisions, 130+ Roles, & Tool Registry).
"""

DDL_CORPORATE_DIVISIONS = """
CREATE TABLE IF NOT EXISTS corporate_divisions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    purpose TEXT NOT NULL,
    accent_color TEXT NOT NULL DEFAULT '#3B82F6',
    icon_name TEXT NOT NULL DEFAULT 'Cpu',
    order_index INTEGER NOT NULL DEFAULT 0
);
"""

DDL_TOOL_PERMISSIONS_REGISTRY = """
CREATE TABLE IF NOT EXISTS tool_permissions_registry (
    tool_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    parameters_json_schema TEXT NOT NULL,
    risk_tier INTEGER NOT NULL DEFAULT 1,
    requires_human_approval INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_ROLES = """
CREATE TABLE IF NOT EXISTS corporate_roles (
    id TEXT PRIMARY KEY,
    division_id TEXT NOT NULL REFERENCES corporate_divisions(id) ON DELETE CASCADE,
    handle_mention TEXT NOT NULL,
    name TEXT NOT NULL,
    job_description TEXT NOT NULL,
    persona_prompt TEXT NOT NULL,
    system_prompt_template TEXT NOT NULL,
    model_provider TEXT NOT NULL DEFAULT 'anthropic',
    model_name TEXT NOT NULL DEFAULT 'claude-3-7-sonnet',
    fallback_models_json TEXT NOT NULL DEFAULT '[]',
    temperature REAL NOT NULL DEFAULT 0.2,
    thinking_level TEXT NOT NULL DEFAULT 'medium',
    tool_permissions_json TEXT NOT NULL DEFAULT '[]',
    token_budget_limit INTEGER NOT NULL DEFAULT 350000,
    is_autonomous_spawned INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

INDEX_ROLES_HANDLE = """
CREATE INDEX IF NOT EXISTS idx_roles_handle ON corporate_roles(handle_mention);
"""

INDEX_DIVISIONS_SLUG = """
CREATE INDEX IF NOT EXISTS idx_divisions_slug ON corporate_divisions(slug);
"""

ORGANIZATION_DDL_LIST = [
    DDL_CORPORATE_DIVISIONS,
    DDL_TOOL_PERMISSIONS_REGISTRY,
    DDL_CORPORATE_ROLES,
    INDEX_ROLES_HANDLE,
    INDEX_DIVISIONS_SLUG,
]
