"""
src/config.py
-------------
Configuration module for FinAgent.
Reads settings from environment variables (and optionally a .env file).
Uses pydantic-settings when available, falling back to manual os.environ parsing.
"""

import os

# ---------------------------------------------------------------------------
# Attempt to use pydantic-settings (recommended)
# ---------------------------------------------------------------------------
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        """Application-wide settings resolved from environment variables."""

        # --- Gemini ---
        gemini_api_key: str = ""

        # --- Model ---
        model: str = "gemini-3.8-flash"

        # --- Logging ---
        log_level: str = "INFO"

        # --- Agent behaviour ---
        max_steps: int = 20
        human_escalation_threshold: int = 3

        model_config = SettingsConfigDict(
            env_prefix="",  # no prefix for GEMINI_API_KEY
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            # Map env variable names that differ from field names
            populate_by_name=True,
            extra="ignore",
        )

        # Aliases for non-standard env var names
        @classmethod
        def settings_customise_sources(cls, settings_cls, **kwargs):  # type: ignore[override]
            # Keep default source order: init > env > dotenv > default
            return super().settings_customise_sources(settings_cls, **kwargs)

    # Override env-var aliases manually since pydantic-settings doesn't support
    # per-field env-name without Field(alias=...) in all versions.
    class _Settings(BaseSettings):
        gemini_api_key: str = ""
        model: str = "gemini-3.8-flash"
        log_level: str = "INFO"
        max_steps: int = 20
        human_escalation_threshold: int = 3

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            populate_by_name=True,
            extra="ignore",
        )

        # Custom env-var names
        @classmethod
        def model_fields_env_names(cls):  # type: ignore[override]
            return {
                "gemini_api_key": "GEMINI_API_KEY",
                "log_level": "FINAGENT_LOG_LEVEL",
                "max_steps": "FINAGENT_MAX_STEPS",
                "human_escalation_threshold": "FINAGENT_HUMAN_ESCALATION_THRESHOLD",
            }

    # Build the final Settings by pulling from env directly so aliases work
    # regardless of pydantic-settings version quirks.
    def _build_settings() -> "_Settings":
        return _Settings(
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("FINAGENT_MODEL", "gemini-3.8-flash"),
            log_level=os.environ.get("FINAGENT_LOG_LEVEL", "INFO"),
            max_steps=int(os.environ.get("FINAGENT_MAX_STEPS", "20")),
            human_escalation_threshold=int(
                os.environ.get("FINAGENT_HUMAN_ESCALATION_THRESHOLD", "3")
            ),
        )

    settings = _build_settings()

except ImportError:
    # ---------------------------------------------------------------------------
    # Fallback: plain dataclass-style object populated from os.environ
    # ---------------------------------------------------------------------------
    class _FallbackSettings:  # type: ignore[no-redef]
        """Fallback settings when pydantic-settings is not installed."""

        def __init__(self) -> None:
            self.gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
            self.model: str = os.environ.get("FINAGENT_MODEL", "gemini-3.8-flash")
            self.log_level: str = os.environ.get("FINAGENT_LOG_LEVEL", "INFO")
            self.max_steps: int = int(os.environ.get("FINAGENT_MAX_STEPS", "20"))
            self.human_escalation_threshold: int = int(
                os.environ.get("FINAGENT_HUMAN_ESCALATION_THRESHOLD", "3")
            )

        def __repr__(self) -> str:  # pragma: no cover
            return (
                f"Settings(model={self.model!r}, log_level={self.log_level!r}, "
                f"max_steps={self.max_steps}, "
                f"human_escalation_threshold={self.human_escalation_threshold})"
            )

    settings: _FallbackSettings = _FallbackSettings()  # type: ignore[assignment]
