"""
Schema DDL: Workboard (Projects, Dynamic Runbooks, Kanban Swarm Tickets, Artifacts, & PR Reviews).
"""

DDL_PROJECTS = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    founder_vision TEXT NOT NULL,
    product_archetype TEXT NOT NULL,
    active_runbook_id TEXT REFERENCES corporate_runbooks(id),
    active_sandbox_profile TEXT NOT NULL DEFAULT 'profile-web-saas',
    status TEXT NOT NULL DEFAULT 'DISCOVERY',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_RUNBOOKS = """
CREATE TABLE IF NOT EXISTS corporate_runbooks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    dag_stages_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_TICKETS = """
CREATE TABLE IF NOT EXISTS corporate_tickets (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_ticket_id TEXT REFERENCES corporate_tickets(id),
    assigned_role_id TEXT NOT NULL REFERENCES corporate_roles(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'BACKLOG',
    priority TEXT NOT NULL DEFAULT 'MEDIUM',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    blackboard_json TEXT NOT NULL DEFAULT '[]',
    active_file_path TEXT,
    live_scratchpad_text TEXT,
    status_bubble_text TEXT,
    artifact_refs_json TEXT NOT NULL DEFAULT '[]',
    retry_count INTEGER NOT NULL DEFAULT 0,
    consultation_turns INTEGER NOT NULL DEFAULT 0,
    spent_tokens INTEGER NOT NULL DEFAULT 0,
    spent_cost_usd REAL NOT NULL DEFAULT 0.0,
    lease_owner TEXT,
    lease_expires_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_PROJECT_ARTIFACTS = """
CREATE TABLE IF NOT EXISTS project_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ticket_id TEXT REFERENCES corporate_tickets(id),
    producer_role_id TEXT NOT NULL REFERENCES corporate_roles(id),
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_PULL_REQUESTS = """
CREATE TABLE IF NOT EXISTS corporate_pull_requests (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ticket_id TEXT NOT NULL REFERENCES corporate_tickets(id),
    author_role_id TEXT NOT NULL REFERENCES corporate_roles(id),
    diff_content TEXT NOT NULL,
    lsp_diagnostics_json TEXT NOT NULL DEFAULT '[]',
    owasp_findings_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_CORPORATE_PR_REVIEWS = """
CREATE TABLE IF NOT EXISTS corporate_pr_reviews (
    id TEXT PRIMARY KEY,
    pr_id TEXT NOT NULL REFERENCES corporate_pull_requests(id) ON DELETE CASCADE,
    reviewer_role_id TEXT NOT NULL REFERENCES corporate_roles(id),
    verdict TEXT NOT NULL,
    security_score INTEGER NOT NULL DEFAULT 100,
    comments_json TEXT NOT NULL DEFAULT '[]',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

INDEX_TICKETS_PROJECT_STATUS = """
CREATE INDEX IF NOT EXISTS idx_tickets_proj_stat ON corporate_tickets(project_id, status);
"""

WORKBOARD_DDL_LIST = [
    DDL_PROJECTS,
    DDL_CORPORATE_RUNBOOKS,
    DDL_CORPORATE_TICKETS,
    DDL_PROJECT_ARTIFACTS,
    DDL_CORPORATE_PULL_REQUESTS,
    DDL_CORPORATE_PR_REVIEWS,
    INDEX_TICKETS_PROJECT_STATUS,
]
