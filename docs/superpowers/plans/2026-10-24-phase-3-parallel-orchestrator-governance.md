# SovereignOS Phase 3: Parallel Orchestrator, Backend Global Oasis & Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the parallel orchestration engine, real-time `/office` event bus, executive `@secretary` 3-gear dispatcher, autonomous Kanban swarm runner, and governance guardrails (Circuit Breaker, FinOps, PR Quorum Gate, Flight Recorder) for SovereignOS.

**Architecture:** An asynchronous event-driven control plane using Python 3.12, SQLite WAL (`aiosqlite`) with atomic queries and path-level async mutexes, adhering to the 3-Tier Flat Matrix topology (Executive Brain Trust -> Parallel Talent Pools -> Independent Gatekeepers) with zero token idle overhead. All modules follow the Facade + Siblings pattern (<= 250-300 LOC) and strict Test-Driven Development (TDD).

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, `aiosqlite` (WAL mode), `asyncio`, `pytest`, `pytest-asyncio`. (Strictly pure-native: zero LangChain/CrewAI/vendor SDKs).

**Spec:**
- `Arsitektur.md` (Topologi 4-Lapisan, 2D Web Control Plane, 3-Tier Flat Matrix)
- `Database.md` (28 Skema DDL: `corporate_tickets`, `projects`, `corporate_runbooks`, `corporate_pull_requests`, `corporate_token_ledger`, `venture_financial_ledger`, `corporate_messages`)
- `Pipeline-Communication.md` (4-Category Event Bus, Scoped `@mention` Isolation, 1-Click Hold Ticket, War Room)
- `Gemini.md` (10 Invarian Arsitektur Suci)
- `Secretary-Role.md` (3-Gear Command Dispatcher & `@tool_builder` Integration)
- `Roadmap.md` (Fase 3 Deliverables)

---

## Global Constraints & Mandatory Guidelines

- **Max LOC per file:** 250–300 lines (strictly no God files; enforce Facade + Siblings).
- **Runtime:** Python 3.12+ with strict typing annotations.
- **Full Native:** No LangChain, CrewAI, AutoGen, LlamaIndex, or vendor SDKs (`openai`, `anthropic`, `google-genai`). All model calls via HTTPX/SovereignModelRouter.
- **Database:** Dual-Engine SQLite WAL (`aiosqlite`) / asyncpg, single-writer state lease, atomic SQL queries (`UPDATE ... WHERE ... RETURNING *`).
- **PRAGMA foreign_keys = ON Compliance in Tests:** Parent rows (`projects`, `corporate_divisions`, `corporate_roles`) must be seeded before creating child rows (`corporate_tickets`, `corporate_pull_requests`, `venture_financial_ledger`).
- **1-Click Hold Ticket Integration:** `hold_ticket_action()` in `office_dispatch.py` must set ticket status to `ON_HOLD`, trigger an interrupt signal registered with `turn_preflight.py`, and release active locks in `FileLockManager`.
- **Zero Branch Tables:** Branch table concept is discarded as per `Database.md`; `branch_merge_lca.py` is removed.
- **3-Wave TDD Execution:** Work is executed and verified in 3 sequential waves:
  - **Gelombang 3A:** Task 1, 2, & 3
  - **Gelombang 3B:** Task 4, 5, & 6
  - **Gelombang 3C:** Task 7, 8, & 9

---

## Review Focus

1. **Path-Level File Locking Deadlock & Path Normalization**: Concurrent agents acquiring locks on equivalent relative vs absolute paths (`lib/main.dart` vs `./lib/main.dart`) must resolve to the identical mutex key to prevent data races.
2. **Orphaned Lease Recovery**: Worker process crash or ungraceful termination while holding `IN_PROGRESS` lease must be detected and safely transitioned back to `READY` by the heartbeat lease watchdog.
3. **Instant 1-Click Hold Preemption & Lock Release**: When Founder triggers `hold_ticket_action()`, the active worker must abort cleanly via interrupt signal before subsequent model calls, and its held file locks must be immediately released.
4. **Discussion Loop Freeze (Circuit Breaker)**: Inter-agent ping-pong consultations reaching 3 turns without producing new code or artifacts must freeze to `BLOCKED_LOOP_DETECTED` and alert `CEO_DECISION_GATES`.
5. **FinOps Dual-Ledger Synchronization**: Token consumption must update `corporate_token_ledger` and trigger budget freeze without corrupting real-world venture financial entries in `venture_financial_ledger`.

---

# GELOMBANG 3A: Orchestrator Primitives, Office Telemetry & Runbook DAG

### Task 1: Orchestrator Core Primitives (`file_lock_manager.py` & `event_bus.py`)

**Files:**
- Create: `backend/app/engine/orchestrator/file_lock_manager.py`
- Modify: `backend/app/engine/orchestrator/event_bus.py`
- Test: `backend/tests/test_orchestrator_primitives.py`

**Interfaces:**
- Consumes: `app.db.session.get_db_connection`, `app.db.repos.message_repo.insert_message`
- Produces:
  - `FileLockManager.acquire(project_id: str, file_path: str) -> None`
  - `FileLockManager.release(project_id: str, file_path: str) -> None`
  - `FileLockManager.release_all_project_locks(project_id: str) -> int`
  - `FileLockManager.lock(project_id: str, file_path: str) -> AsyncContextManager`
  - `CorporateEventBus.subscribe(project_id: str, category: Optional[str]) -> asyncio.Queue`
  - `CorporateEventBus.unsubscribe(project_id: str, queue: asyncio.Queue) -> None`
  - `CorporateEventBus.publish(conn: aiosqlite.Connection, project_id: str, stream_category: str, event_type: str, content: str, sender_role_id: Optional[str], scoped_recipient_role_id: Optional[str], metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]`

- [ ] **Step 1: Write failing tests for FileLockManager and CorporateEventBus**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_orchestrator_primitives.py -v`)**
- [ ] **Step 3: Implement `FileLockManager` and `CorporateEventBus`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_orchestrator_primitives.py -v`)**
- [ ] **Step 5: Commit**

---

### Task 2: Office Backend & Live Telemetry (`office_relay.py`, `office_dispatch.py`, `war_room_moderator.py`)

**Files:**
- Create: `backend/app/engine/office/office_relay.py`
- Create: `backend/app/engine/office/office_dispatch.py`
- Create: `backend/app/engine/office/war_room_moderator.py`
- Modify: `backend/app/engine/turn/turn_preflight.py` (Add global interrupt registry check)
- Test: `backend/tests/test_office_engine.py`

**Interfaces:**
- Consumes: `app.engine.orchestrator.event_bus.corporate_event_bus`, `app.db.repos.ticket_repo`, `app.engine.orchestrator.file_lock_manager.file_lock_manager`, `app.engine.turn.turn_preflight`
- Produces:
  - `OfficeRelay.emit_screenshare_telemetry(conn: aiosqlite.Connection, ticket_id: str, role_handle: str, status_bubble: str, active_file_path: Optional[str], live_scratchpad: Optional[str], live_diff_preview: Optional[str]) -> Dict[str, Any]`
  - `OfficeDispatch.hold_ticket_action(conn: aiosqlite.Connection, project_id: str, ticket_id: str) -> Dict[str, Any]` (Sets `ON_HOLD`, sets interrupt signal in preflight, releases file locks)
  - `OfficeDispatch.resume_ticket_action(conn: aiosqlite.Connection, ticket_id: str) -> Dict[str, Any]`
  - `WarRoomModerator.start_war_room_session(conn: aiosqlite.Connection, project_id: str, founder_problem: str, participants: List[str]) -> List[Dict[str, Any]]`

- [ ] **Step 1: Write failing tests for Office engine (with parent FK seeding: project, division, roles)**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_office_engine.py -v`)**
- [ ] **Step 3: Implement `office_relay.py`, `office_dispatch.py`, and `war_room_moderator.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_office_engine.py -v`)**
- [ ] **Step 5: Commit**

---

### Task 3: Dynamic Runbook DAG & Project Repositories (`project_repo.py`, `runbook_dag.py`)

**Files:**
- Create: `backend/app/db/repos/project_repo.py`
- Create: `backend/app/engine/orchestrator/runbook_dag.py`
- Test: `backend/tests/test_runbook_dag.py`

**Interfaces:**
- Consumes: `app.db.session.get_db_connection`, `Database.md` tables `projects`, `corporate_runbooks`, `corporate_roles`
- Produces:
  - `create_project(conn: aiosqlite.Connection, id: str, name: str, founder_vision: str, product_archetype: str, sandbox_profile: str) -> Dict[str, Any]`
  - `get_project(conn: aiosqlite.Connection, project_id: str) -> Optional[Dict[str, Any]]`
  - `create_runbook(conn: aiosqlite.Connection, id: str, name: str, description: str, dag_stages: List[Dict[str, Any]]) -> Dict[str, Any]`
  - `RunbookDAGEngine.compile_runbook_to_tickets(conn: aiosqlite.Connection, project_id: str, runbook_id: str) -> List[Dict[str, Any]]`
  - `RunbookDAGEngine.get_ready_stages(completed_stages: Set[str], dag_stages: List[Dict[str, Any]]) -> List[Dict[str, Any]]`

- [ ] **Step 1: Write failing tests for project repo and Runbook DAG compilation**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_runbook_dag.py -v`)**
- [ ] **Step 3: Implement `project_repo.py` and `runbook_dag.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_runbook_dag.py -v`)**
- [ ] **Step 5: Commit**

---

# GELOMBANG 3B: Kanban Swarm, Delegation Tree & @secretary Dispatcher

### Task 4: Autonomous Kanban Swarm Runner (`kanban_swarm.py`)

**Files:**
- Create: `backend/app/engine/orchestrator/kanban_swarm.py`
- Test: `backend/tests/test_kanban_swarm.py`

**Interfaces:**
- Consumes: `app.db.repos.ticket_repo.claim_ready_ticket`, `app.engine.roles.dynamic_node.DynamicNode`, `app.engine.orchestrator.event_bus.corporate_event_bus`
- Produces:
  - `AutonomousKanbanSwarm.scan_and_claim_tickets(conn: aiosqlite.Connection, project_id: str) -> List[Dict[str, Any]]`
  - `AutonomousKanbanSwarm.check_and_update_dependencies(conn: aiosqlite.Connection, project_id: str) -> int`
  - `AutonomousKanbanSwarm.reclaim_expired_leases(conn: aiosqlite.Connection, project_id: str) -> int`
  - `AutonomousKanbanSwarm.execute_claimed_ticket(conn: aiosqlite.Connection, project_id: str, ticket_id: str, role_id: str) -> bool`

- [ ] **Step 1: Write failing tests for Kanban Swarm Runner (with FK seeding)**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_kanban_swarm.py -v`)**
- [ ] **Step 3: Implement `kanban_swarm.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_kanban_swarm.py -v`)**
- [ ] **Step 5: Commit**

---

### Task 5: Hierarchical Delegation & Autonomous Role Spawning (`delegation_tree.py`, `role_spawner.py`)

**Files:**
- Create: `backend/app/engine/orchestrator/delegation_tree.py`
- Create: `backend/app/engine/roles/role_spawner.py`
- Test: `backend/tests/test_delegation_and_spawner.py`

**Interfaces:**
- Consumes: `Database.md` tables `corporate_tickets`, `corporate_roles`, `corporate_divisions`
- Produces:
  - `DelegationTree.delegate_subtask(conn: aiosqlite.Connection, project_id: str, parent_ticket_id: str, assigned_role_id: str, title: str, description: str, acceptance_criteria: str) -> Dict[str, Any]`
  - `DelegationTree.check_subtasks_completed(conn: aiosqlite.Connection, parent_ticket_id: str) -> bool`
  - `RoleSpawner.spawn_role(conn: aiosqlite.Connection, division_id: str, handle_mention: str, name: str, job_description: str, persona_prompt: str, system_prompt_template: str, tool_permissions: List[str]) -> Dict[str, Any]`

- [ ] **Step 1: Write failing tests for Delegation Tree and Role Spawner (with FK seeding)**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_delegation_and_spawner.py -v`)**
- [ ] **Step 3: Implement `delegation_tree.py` and `role_spawner.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_delegation_and_spawner.py -v`)**
- [ ] **Step 5: Commit**

---

### Task 6: Executive Secretary & 3-Gear Dispatcher (`secretary_dispatcher.py` & `@tool_builder`)

**Files:**
- Create: `backend/app/engine/roles/secretary_dispatcher.py`
- Test: `backend/tests/test_secretary_3gear.py`

**Interfaces:**
- Consumes: `Secretary-Role.md`, `app.engine.roles.mention_relay.dispatch_scoped_mention`, `app.db.repos.project_repo`, `app.engine.orchestrator.runbook_dag`
- Produces:
  - `SecretaryDispatcher.dispatch_command(conn: aiosqlite.Connection, user_prompt: str, founder_id: str) -> Dict[str, Any]`
  - `SecretaryDispatcher.gear_1_personal_assistant(conn: aiosqlite.Connection, prompt: str) -> Dict[str, Any]`
  - `SecretaryDispatcher.gear_2_expert_consultation(conn: aiosqlite.Connection, target_role_handle: str, question: str) -> Dict[str, Any]`
  - `SecretaryDispatcher.gear_3_project_deployment(conn: aiosqlite.Connection, project_name: str, vision: str, archetype: str) -> Dict[str, Any]`
  - `SecretaryDispatcher.delegate_to_tool_builder(conn: aiosqlite.Connection, tool_request_spec: Dict[str, Any]) -> Dict[str, Any]`

- [ ] **Step 1: Write failing tests for Secretary 3-Gear Dispatcher (with FK seeding)**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_secretary_3gear.py -v`)**
- [ ] **Step 3: Implement `secretary_dispatcher.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_secretary_3gear.py -v`)**
- [ ] **Step 5: Commit**

---

# GELOMBANG 3C: Governance Guardrails, PR Quorum Gate & Full Integration

### Task 7: Anti-Loop Circuit Breaker & Multi-Tier FinOps Guardrails (`circuit_breaker.py`, `financial_guardrail.py`, `finance_repo.py`)

**Files:**
- Create: `backend/app/db/repos/finance_repo.py`
- Create: `backend/app/engine/governance/circuit_breaker.py`
- Create: `backend/app/engine/governance/financial_guardrail.py`
- Test: `backend/tests/test_governance_guardrails.py`

**Interfaces:**
- Consumes: `Database.md` tables `corporate_token_ledger`, `venture_financial_ledger`, `corporate_tickets`
- Produces:
  - `record_token_spend(conn: aiosqlite.Connection, project_id: str, ticket_id: str, role_id: str, model_provider: str, model_name: str, prompt_tokens: int, cached_prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None`
  - `record_venture_financial_entry(conn: aiosqlite.Connection, project_id: str, entry_type: str, amount_usd: float, period_month: str, notes: str, recorded_by_role_id: str) -> Dict[str, Any]`
  - `get_venture_pnl_summary(conn: aiosqlite.Connection, project_id: str, period_month: str) -> Dict[str, Any]`
  - `AgentCircuitBreaker.record_consultation_turn(conn: aiosqlite.Connection, ticket_id: str, sender_role: str, recipient_role: str, topic_summary: str) -> bool`
  - `AgentCircuitBreaker.execute_ceo_override(conn: aiosqlite.Connection, ticket_id: str, action: str, directive: Optional[str]) -> Dict[str, Any]`
  - `FinancialCircuitBreaker.check_and_enforce_budget(conn: aiosqlite.Connection, ticket_id: str, tokens_spent: int, cost_usd: float) -> bool`
  - `FinancialCircuitBreaker.approve_founder_budget_topup(conn: aiosqlite.Connection, ticket_id: str, additional_tokens: int, additional_cost: float) -> None`

- [ ] **Step 1: Write failing tests for Circuit Breaker and FinOps guardrails (with FK seeding)**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_governance_guardrails.py -v`)**
- [ ] **Step 3: Implement `finance_repo.py`, `circuit_breaker.py`, and `financial_guardrail.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_governance_guardrails.py -v`)**
- [ ] **Step 5: Commit**

---

### Task 8: P2P Pull Request Quorum & Blackbox Flight Recorder (`pr_repo.py`, `pr_quorum_engine.py`, `flight_recorder.py`)

**Files:**
- Create: `backend/app/db/repos/pr_repo.py`
- Create: `backend/app/engine/governance/pr_quorum_engine.py`
- Create: `backend/app/engine/governance/flight_recorder.py`
- Test: `backend/tests/test_pr_quorum_and_flight_recorder.py`

**Interfaces:**
- Consumes: `Database.md` tables `corporate_pull_requests`, `corporate_pr_reviews`, `project_artifacts`
- Produces:
  - `PRRepository.create_pr(conn: aiosqlite.Connection, pr_id: str, project_id: str, ticket_id: str, author_role_id: str, diff_content: str, lsp_diagnostics: Optional[List[Dict[str, Any]]], owasp_findings: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]`
  - `PRQuorumEngine.submit_review(conn: aiosqlite.Connection, pr_id: str, reviewer_role_id: str, verdict: str, security_score: int, comments: List[str]) -> Dict[str, Any]`
  - `PRQuorumEngine.evaluate_quorum(conn: aiosqlite.Connection, pr_id: str) -> bool`
  - `FlightRecorder.record_step(project_id: str, agent_role: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]`
  - `FlightRecorder.replay_step(project_id: str, step_index: int) -> Optional[Dict[str, Any]]`

- [ ] **Step 1: Write failing tests for PR Quorum and Flight Recorder (with FK seeding)**
- [ ] **Step 2: Run test to verify it fails (`pytest tests/test_pr_quorum_and_flight_recorder.py -v`)**
- [ ] **Step 3: Implement `pr_repo.py`, `pr_quorum_engine.py`, and `flight_recorder.py`**
- [ ] **Step 4: Run test to verify it passes (`pytest tests/test_pr_quorum_and_flight_recorder.py -v`)**
- [ ] **Step 5: Commit**

---

### Task 9: Phase 3 Integration & End-to-End Orchestration Verification

**Files:**
- Create: `backend/tests/test_phase3_full_integration.py`
- Modify: `backend/app/engine/__init__.py`

**Interfaces:**
- Consumes: All Phase 3 modules from Tasks 1 through 8.
- Produces: Integrated end-to-end multi-agent orchestration cycle test.

- [ ] **Step 1: Write end-to-end integration test (with FK seeding)**
- [ ] **Step 2: Run all Phase 1, Phase 2, and Phase 3 tests to verify entire test suite passes (`pytest -v`)**
- [ ] **Step 3: Commit Phase 3 completion**

---

## Self-Review Checklist

1. **Spec Coverage:**
   - `event_bus.py` (4 stream channels) & `file_lock_manager.py` covered in Task 1.
   - `office_relay.py`, `office_dispatch.py`, `war_room_moderator.py` covered in Task 2.
   - `runbook_dag.py` and `project_repo.py` covered in Task 3.
   - `kanban_swarm.py` with atomic claim and heartbeat leases covered in Task 4.
   - `delegation_tree.py` and `role_spawner.py` covered in Task 5.
   - `@secretary` 3-Gear Dispatcher and `@tool_builder` covered in Task 6.
   - `circuit_breaker.py`, `financial_guardrail.py`, and `finance_repo.py` covered in Task 7.
   - `pr_quorum_engine.py` and `flight_recorder.py` covered in Task 8 (with `branch_merge_lca.py` deleted).
   - Full integration verification in Task 9.

2. **Step Scan:** Every task strictly defines Step 1 (Write failing test), Step 2 (Run to verify fail), Step 3 (Minimal implementation), Step 4 (Run to verify pass), and Step 5 (Commit).

3. **Type Consistency:** Method signatures across tasks (`claim_ready_ticket`, `hold_ticket_action`, `record_consultation_turn`, `submit_review`) match existing signatures in `ticket_repo.py` and `Database.md`.

4. **Review Focus Coverage:**
   - Path normalization verified in Task 1 test (`test_file_lock_manager_mutex_and_normalization`).
   - Orphaned lease recovery verified in Task 4.
   - Instant hold preemption and lock release verified in Task 2 and Task 9.
   - Discussion loop 3-turn freeze verified in Task 7.
   - FinOps dual-ledger synchronization verified in Task 7.
