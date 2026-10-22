"""
SovereignOS Configuration Settings.
Mengelola konfigurasi sistem, path data, dan kredensial lingkungan.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR.parent


class Settings(BaseModel):
    """Konfigurasi inti Sovereign OS."""

    APP_NAME: str = "Sovereign OS"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # Storage & Database
    DATABASE_URL: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{PROJECT_ROOT}/data/sovereign.db")
    )
    POSTGRES_DSN: Optional[str] = Field(default_factory=lambda: os.getenv("POSTGRES_DSN"))

    # Security & Vault
    VAULT_MASTER_KEY: str = Field(
        default_factory=lambda: os.getenv("VAULT_MASTER_KEY", "sovereign_default_insecure_vault_key_32b_!")
    )
    TELEGRAM_STEALTH_PIN: str = Field(
        default_factory=lambda: os.getenv("TELEGRAM_STEALTH_PIN", "999888")
    )

    # Paths
    CATALOG_DIR: Path = Field(default_factory=lambda: (PROJECT_ROOT / "catalog").resolve())
    DATA_DIR: Path = Field(default_factory=lambda: (PROJECT_ROOT / "data").resolve())

    # Provider Base URLs (Default Fallbacks)
    OPENAI_BASE_URL: str = Field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    ANTHROPIC_BASE_URL: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
    GEMINI_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
    )
    DEEPSEEK_BASE_URL: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
    GROQ_BASE_URL: str = Field(default_factory=lambda: os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    OLLAMA_BASE_URL: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    OPENROUTER_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    TOKENOMIX_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("TOKENOMIX_BASE_URL", "https://api.tokenomixai.com/v1")
    )
    OPENAI_COMPATIBLE_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.tokenomixai.com/v1")
    )

    # Chain-of-Verification (CoV) Configuration
    # Mode pilihan: "llm" (Full LLM Critic) atau "jev" (TypeSafe AI System One Jev)
    COV_MODE: str = Field(default_factory=lambda: os.getenv("COV_MODE", "llm"))
    TYPESAFE_API_KEY: Optional[str] = Field(default_factory=lambda: os.getenv("TYPESAFE_API_KEY"))
    TYPESAFE_BASE_URL: str = Field(
        default_factory=lambda: os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai/v1")
    )
    TYPESAFE_JEV_MODEL: str = Field(
        default_factory=lambda: os.getenv("TYPESAFE_JEV_MODEL", "jev-1")
    )


settings = Settings()
