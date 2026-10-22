# SovereignOS

**Universal Autonomous Multi-Agent Corporate Operating System**

SovereignOS is an enterprise-grade autonomous operating system designed for a **Solo Founder (CEO)** to plan, architect, build, audit, and launch full-lifecycle digital products across any domain—including Web/SaaS, Mobile Apps (Flutter/Android), 2D/3D Game Development, Creative Media (4K Canvas/Poster Design), Deep Market Research, and Universal Publishing.

---

## Key Architectural Highlights

- **10-Phase Cognitive Turn Loop**: Deterministic agent cognitive cycle (Preflight Check $\rightarrow$ Cache Boundary Request Assembly $\rightarrow$ Watchdog API Call $\rightarrow$ Reasoning Extraction $\rightarrow$ Dynamic RBAC Validation $\rightarrow$ Pre-Flight Chain-of-Verification $\rightarrow$ Sandbox Execution $\rightarrow$ State Finalization & Anti-Loop Circuit Breaker).
- **Byte-Stable Prompt Cache Boundary**: Enforces strict prefix determinism (`<!-- SOVEREIGN_CACHE_BOUNDARY -->`) with alphabetized tool schemas to maximize LLM cache hit rates (90%+ cache savings on Anthropic, Gemini, and DeepSeek).
- **Dual-Mode Chain-of-Verification (CoV)**:
  - **Mode LLM Critic**: Semantic reasoning audit using frontier language models.
  - **Mode TypeSafe AI Jev**: High-speed (70–500ms) System One probabilistic decision engine with 0% type hallucinations and free output tokens.
  - **Non-Hijacking Worker Self-Repair**: Enforces Invariant 8—guardrails never mutate agent parameters directly; feedback is returned to the agent for autonomous repair.
- **130+ Digital Agency Roles**: Pre-configured specialized agents across 16 corporate divisions (`catalog/agents`) mapped to 7-phase execution runbooks.
- **Executive Personal Assistant (`@secretary`)**: Omnichannel bridge connecting the Founder via Telegram/WhatsApp to the multi-agent swarm for mobile status monitoring, voice/text briefing, and crisis escalation.
- **Native Polyglot Core**: 100% native implementation with Python 3.12, FastAPI, Pydantic v2, and `aiosqlite` (SQLite WAL) with zero vendor-SDK bloat (no LangChain, no vendor libraries).

---

## Directory Structure Overview

```text
SovereignOS/
├── backend/
│   ├── app/
│   │   ├── core/         # Settings, AES-256 Vault, Logger, Concurrency
│   │   ├── db/           # Repositories & DDL Schemas (SQLite WAL / PostgreSQL)
│   │   ├── engine/       # Turn Loop, Roles, Governance (CoV & Jev), Tools
│   │   └── gateway/      # Prompt Cache Boundary, Model Router, Native Adapters
│   ├── tests/            # Comprehensive integration and unit test suite
│   └── demo_turn_engine.py
├── catalog/
│   ├── agents/           # 130+ specialized agent prompt catalogs (.md)
│   ├── playbooks/        # 7-phase product development playbooks (.md)
│   ├── coordination/     # Dynamic handoff & activation protocols
│   ├── divisions.json    # Corporate divisions schema
│   ├── runbooks.json     # Multi-phase execution DAG definitions
│   └── tools.json        # Tool catalog registry
├── crates/               # Rust Security Sandbox Sidecars
├── sandboxes/            # Isolated execution sandbox profiles
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+ (Python 3.12 recommended)
- Astral `uv` or `pip`

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/HillarioRZA/SovereignOS.git
   cd SovereignOS
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your LLM API keys (e.g. Anthropic, Gemini, DeepSeek, Tokenomix, etc.)
   ```

3. **Install Dependencies & Run Backend**:
   ```bash
   cd backend
   pip install -e .
   ```

4. **Verify Test Suite**:
   ```bash
   python -m pytest -v
   ```

5. **Run Interactive Engine Demo**:
   ```bash
   python demo_turn_engine.py
   ```

---

## License

Proprietary & Confidential — All Rights Reserved.
Created by [HillarioRZA](https://github.com/HillarioRZA).
