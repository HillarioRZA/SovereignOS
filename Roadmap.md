# IMPLEMENTATION ROADMAP & ARCHITECTURAL STRATEGY — SOVEREIGN OS

## 1. Strategi Urutan Pembangunan
1. **Engine & Orchestrator First (Fase 1–4)**: Membangun inti database Dual-Engine, ingesti 130+ agen `agency-agents`, *10-Phase Turn Loop*, *Byte-Stable Prompt Cache*, *Kanban Swarm*, serta *Office Relay / Scoped `@mention` / War Room Engine* terlebih dahulu menggunakan `MockToolExecutor` dan 3 primitif dasar (Koordinasi Kanban, File I/O Ber-mutex, & PTC Kernel)[cite: 2, 3, 4, 5].
2. **Memory & Self-Evolution (Fase 5)**: Menghidupkan *Hybrid RAG*, *3-Stage Cognitive Dreaming*, dan *Closed Learning Loop* (`skill_manage` + `curator.py`)[cite: 2, 3, 4].
3. **Modular Tools via DB Permission & 2D Obsidian Command HQ (Fase 6)**: Mendaftarkan perkakas spesifik domain (Web, Flutter/Android, Playwright CDP Canvas, Image/Video Gen, MCP) sebagai izin di tabel `tool_permissions_registry` dan menyempurnakan antarmuka **2D Obsidian Liquid Global Oasis (`/office`)**[cite: 1, 2, 3, 4].

---

## 2. Peta Jalan Implementasi Bertahap (6 Fase)

### FASE 1: Fondasi Database Dual-Engine, Keamanan Inti & Ingesti Katalog `agency-agents`
- [x] Inisialisasi struktur monorepo dan manajer paket `uv` dengan aturan keamanan 3-hari (`exclude-newer = "3 days"`)[cite: 2].
- [x] Implementasi `db/session.py` (SQLite WAL + opsi PostgreSQL), `state_lease.py` (*Single-Writer Lease* + *Heartbeat*), `read_pool.py` (*FD-aware*), dan `quarantine_repair.py` (*Sidecar WAL Guard*)[cite: 2, 3, 4].
- [x] Cangkok `security.py` (AES-256-GCM Vault), `secret_scope.py` (isolasi profil multi-tenant), dan `auth_manager.py` (Stealth PIN Telegram)[cite: 2, 3].
- [x] Bangun tabel `tool_permissions_registry` beserta `MockToolExecutor`.
- [x] Bangun `agency_loader.py` untuk mem-parsing `divisions.json`, `tools.json`, `runbooks.json`, 7 fase `playbooks/`, dan 130+ file `.md` dari `catalog/` ke tabel `corporate_divisions`, `corporate_roles` (lengkap dengan `handle_mention`), dan `corporate_runbooks`[cite: 3, 5].

### FASE 2: Cognitive Engine, 10-Phase Turn Loop & Byte-Stable Prompt Gateway
- [x] Bangun `cache_boundary.py` (`splitSystemPromptCacheBoundary` + pengurutan alfabetis skema tool dari DB + pelacak hash SHA-256 `system_prompt_digest`)[cite: 2, 4].
- [x] Bangun `SovereignModelRouter` (`model_router.py`: 30+ provider, Nous Portal, RPM/TPM throttling, Auto-Cooldown 429, Cost-IQ Escalation, dan `tool_call_repair.py`)[cite: 2, 3, 4].
- [x] Bangun **10-Phase Turn Loop** (`engine/turn/turn_*.py`: preflight dengan pengecekan status `ON_HOLD`, request assembly, API call + watchdog, tool validation, two-tier context compaction + loop guard, finalizer)[cite: 2, 4].
- [x] Cangkok & sempurnakan **Chain-of-Verification (CoV) Gatekeeper** (`cov_verifier.py`, `jev_client.py`, `Chain-of-Verification.md`):
  * **Otonomi Peran**: Agen mandiri memeriksa respons; jika tanpa pemanggilan perkakas, respons langsung dipassthrough ke user/rekan (0-token CoV overhead).
  * **Dua Mode Terintegrasi (Toggleable)**: Mendukung **Mode LLM Critic** (evaluasi semantik skema) dan **Mode TypeSafe AI Jev** (*System One* probabilistic decision, 70–500ms, 0% halusinasi, $0 output tokens).
  * **Invarian Suci 8**: Penegakan ketat *Non-Hijacking Worker Self-Repair Loop* (CoV dilarang mengubah parameter sendiri; wajib memberikan umpan balik agar agen pekerja merevisi mandiri), pencegahan *path traversal*, dan audit log permanen ke `sentinel_audit_logs`[cite: 2, 3].

### FASE 3: Parallel Orchestrator, Backend Global Oasis (`/office`) & Governance Guardrails
- [x] Bangun `event_bus.py` (mendukung 4 kategori stream: `ALL`, `EXECUTION_HANDOFFS`, `CEO_DECISION_GATES`, `OASIS_LOUNGE` dengan 0-token idle overhead) dan `file_lock_manager.py` (*Path-level async mutex*)[cite: 1, 3].
- [x] Bangun modul `engine/office/`:
  - `office_relay.py` & `mention_relay.py` (injeksi instruksi `@mention` terisolasi ke agen sasaran & pancaran *Screen-Share* `active_file_path` + `live_scratchpad_text`)[cite: 1, 3].
  - `office_dispatch.py` (penanganan aksi 1-klik **Hold Ticket** untuk membekukan tiket ke status `ON_HOLD`, interupsi preflight & rilis file locks)[cite: 1].
  - `war_room_moderator.py` (orkestrasi sesi **All-Hands Executive War Room** yang dimoderasi oleh CoS dan CTO)[cite: 1, 3].
- [x] Bangun `runbook_dag.py` dan `kanban_swarm.py` (*Atomic Claim Query* + *Heartbeat Lease* + topologi *3-Tier Flat Matrix*: Planner $\rightarrow$ Parallel Talent Pools $\rightarrow$ Independent Gatekeepers + *Checkpoint Recovery Loop*)[cite: 2, 3, 4, 5].
- [x] Bangun `delegation_tree.py` (`delegate_task`) dan `role_spawner.py` (*Autonomous Hiring*)[cite: 2, 3].
- [x] Bangun peran eksekutif **`@secretary` (AI Executive Personal Secretary & Omnichannel Companion)**:
  * Logika transmisi **3-Gear Dispatcher**: Gigi 1 Fast-Path Direct Answer (Personal Assistant), Gigi 2 Ad-Hoc Expert Consultation via `builtin:consult_role` & `mention_relay.py`, dan Gigi 3 Direct Project & Ticket Creation (`builtin:create_project`, `builtin:init_project_runbook`, `builtin:create_ticket`).
  * Peran on-demand **`@tool_builder`** (penampungan kebutuhan tools/MCP, pelaporan rutin, eskalasi kebuntuan via `CEO_DECISION_GATES`, dan delegasi perakitan perkakas baru sesuai `Secretary-Role.md`).
- [x] Cangkok `circuit_breaker.py`, `financial_guardrail.py` (integrasi pelacakan ganda: `corporate_token_ledger` untuk FinOps AI dan `venture_financial_ledger` untuk P&L bisnis riil), `pr_quorum_engine.py`, dan `flight_recorder.py` (`branch_merge_lca.py` ditiadakan sesuai penghapusan tabel branch di Database.md)[cite: 3].

### FASE 4: Rust Security Sidecar, BaseEnvironment & PTC Python Kernel
- [ ] Bangun *crate* Rust `sovereign-sandbox-guard` (validasi anti-*symlink traversal*, blokir *mount* sensitif `/etc`, `~/.ssh`, `docker.sock`, sanitasi env) dan `sovereign-node-host` (protokol `OCSC` HMAC-SHA-256)[cite: 4].
- [ ] Bangun `sandbox/base_env.py` (*Unified Spawn-per-Call*, *snapshot re-sourcing* `hermes-snap`, CWD tracker, `fetch_file` base64) dan `snapshot_cow.py` (`AUTO_PRE_ROLLBACK`)[cite: 2, 3].
- [ ] Bangun **In-Sandbox PTC Python Kernel** (`ptc_kernel.py` / `execute_code`) dengan batas *stdout* 50KB dan *spill cache* otomatis ke disk[cite: 2].
- [ ] Aktifkan 11 konektor backend sandbox (Local, Fallback HTTP, QuickJS WASI, Docker + Caddy, Podman, Singularity, Modal GPU, Crabbox Cloud, Vercel, Daytona, OpenShell, SSH, CUA) serta `cli_harness.py` (Claude Code / Codex)[cite: 2, 3, 4].

### FASE 5: Cognitive Memory Dreaming & Closed Learning Loop
- [ ] Bangun `hybrid_rag.py` (FastEmbed ONNX 384-dim + LanceDB + SQLite FTS5 CJK `session_search` dengan partisi isolasi memori harian personal `project_id = 'personal'`) dan `honcho_modeling.py`[cite: 2, 3, 4].
- [ ] Bangun `dreaming_engine.py` (siklus *Light Sleep*, *REM Sleep*, dan *Deep Sleep* dengan *Loss-Fraction Guard*)[cite: 4].
- [ ] Bangun `skill_manager.py` (pembuatan & penambalan mandiri `SKILL.md`), `skill_curator.py` (pengarsipan otomatis berbasis `.usage.json`), dan `tool_synthesizer.py` (diorkestrasi via `@tool_builder`)[cite: 2, 3].

### FASE 6: Modular Domain Tools, Omnichannel, 2D Obsidian Oasis & Native Desktop App
- [ ] **FastAPI Core Endpoints Router (`backend/app/api/v1/`)**:
  - Bangun router REST & WebSocket di `backend/app/api/v1/` (`tickets.py`, `office.py`, `secretary.py`, `finance.py`, `war_room.py`) yang membungkus seluruh engine backend (`office_dispatch`, `office_relay`, `kanban_swarm`, `secretary_dispatcher`, `finance_repo`) ke dalam endpoint HTTP REST dan WebSocket stream (`/api/v1/corporate/ws/office/{project_id}`) untuk diakses oleh Frontend Next.js `/office` dan bot Omnichannel.
- [ ] **Live Dynamic LLM Engine untuk Eksekutif (`war_room_moderator.py` & `secretary_dispatcher.py`)**:
  - Hubungkan `secretary_dispatcher.py` dan `war_room_moderator.py` ke `DynamicNode` / `SovereignModelRouter` untuk penalaran intent dinamis berbasis LLM riil (sesuai `Secretary-Role.md`) dan debat All-Hands multi-turn otonom antar-agen (`@cos`, `@cto`, `@cfo`, `@pm`) dengan live human-in-the-loop Founder interjection, serta mempertahankan logika deterministik sebagai fallback/mock test.
- [ ] Daftarkan dan aktifkan modul *Tools* ke `tool_permissions_registry`:
  - *Engineering & Mobile*: Multi-Lang LSP (`tsc`, `pyright`, `dart analyze`, `kotlinc`), AST OWASP Scanner, Flutter/Gradle Builder, Git Exporter[cite: 3].
  - *Creative & Multimodal*: Playwright Browser CDP + Camofox Stealth, Image/Video/Music Gen (Flux, Fal.ai, ComfyUI, Runway, Suno), Vision Finish Gate Evaluator, PDF Document Compiler[cite: 2, 4, 5].
  - *External Bridges*: Bidirectional MCP Client/Server (`mcp_bridge.py`) dan protokol federasi `@openclaw/a2a` v1.0[cite: 2, 3, 4].
- [ ] Aktifkan Omnichannel Gateway (30+ platform chat terutama integrasi langsung Telegram/WhatsApp dengan **`@secretary`** untuk personal companion ala Hermes/OpenClaw, briefing suara/teks, komando pembuatan proyek/tiket, pemantauan status, dan intervensi darurat Founder)[cite: 2, 4].
- [ ] Bangun dan sempurnakan Frontend Next.js 14:
  - **Global Oasis Live Command HQ (`/office`)**: Antarmuka 2D Obsidian Liquid (`#090d16` / `#0f172a`), 4 tab filter *Live Stream*, konsol `@mention` dengan *auto-completion*, modal *All-Hands Executive War Room*, serta *Live Agent Screen-Share & Code Inspection Pane* dengan tombol 1-klik *Hold Ticket*[cite: 1, 3].
  - **Dashboard FinOps & P&L Bisnis**: Visualisasi perbandingan konsumsi token AI per proyek vs revenue riil dari `venture_financial_ledger`.
  - **Universal Artifact Showcase (`/preview/[id]`)**, React Ink TUI, dan RL Trajectory Exporter[cite: 2, 3, 4].
- [ ] **Packaging Native Desktop App (Tauri .exe untuk Windows)**:
  - Client tipis super-ringan (<20MB RAM, 0% CPU background) yang duduk manis di System Tray Windows laptop Founder.
  - Native toast notifications untuk persetujuan eksekutif CEO Gate, terhubung mulus ke Ubuntu VPS 24/7 melalui jaringan aman Tailscale Zero-Trust.

