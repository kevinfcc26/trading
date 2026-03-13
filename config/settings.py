from pydantic import SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Risk profiles ──────────────────────────────────────────────────────────────
# Set TRADING_PROFILE in .env to select a preset.
# Any individual env var overrides the profile value.
#
# conservative : Low frequency, tight filters, small risk. Good for live with real money.
# moderate     : Balanced. Default. Good for paper trading and early live.
# aggressive   : Higher frequency, looser filters, larger risk. Only for experienced traders.

RISK_PROFILES: dict[str, dict] = {
    "conservative": {
        "risk_per_trade": 0.005,       # 0.5% per trade
        "max_open_positions": 2,
        "min_signal_threshold": 0.58,
        "claude_veto_threshold": 0.75,
        "sr_min_rr_ratio": 2.5,
        "confluence_min_score": 2.5,
        "weight_ta": 0.25,
        "weight_ml": 0.35,
        "weight_claude": 0.40,
    },
    "moderate": {
        "risk_per_trade": 0.015,       # 1.5% per trade
        "max_open_positions": 2,
        "min_signal_threshold": 0.52,
        "claude_veto_threshold": 0.70,
        "sr_min_rr_ratio": 2.0,
        "confluence_min_score": 2.0,
        "weight_ta": 0.25,
        "weight_ml": 0.35,
        "weight_claude": 0.40,
    },
    "aggressive": {
        "risk_per_trade": 0.025,       # 2.5% per trade
        "max_open_positions": 4,
        "min_signal_threshold": 0.45,
        "claude_veto_threshold": 0.80,
        "sr_min_rr_ratio": 1.5,
        "confluence_min_score": 1.5,
        "weight_ta": 0.20,
        "weight_ml": 0.35,
        "weight_claude": 0.45,
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Secrets (always in .env, never in profiles) ───────────────────────────
    anthropic_api_key: SecretStr = SecretStr("")
    mt5_login: int = 0
    mt5_password: SecretStr = SecretStr("")
    mt5_server: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "brocker"
    db_user: str = "brocker"
    db_password: SecretStr = SecretStr("brocker")

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ── AI provider ───────────────────────────────────────────────────────────
    ai_provider: str = "ollama"        # "claude" | "ollama" | "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # ── Trading defaults ──────────────────────────────────────────────────────
    default_symbol: str = "EURUSD"
    default_timeframe: str = "M15"
    dry_run: bool = True
    initial_balance: float = 1000.0

    # ── Risk profile ──────────────────────────────────────────────────────────
    # Set TRADING_PROFILE=conservative|moderate|aggressive in .env
    # Override individual values by setting them explicitly in .env
    trading_profile: str = "moderate"
    risk_per_trade: float | None = None
    max_open_positions: int | None = None
    min_signal_threshold: float | None = None
    claude_veto_threshold: float | None = None
    sr_min_rr_ratio: float | None = None
    confluence_min_score: float | None = None
    weight_ta: float | None = None
    weight_ml: float | None = None
    weight_claude: float | None = None

    @model_validator(mode="after")
    def apply_profile(self) -> "Settings":
        profile = RISK_PROFILES.get(self.trading_profile, RISK_PROFILES["moderate"])
        for field, default in profile.items():
            if getattr(self, field) is None:
                setattr(self, field, default)
        return self

    # ── Multi-timeframe analysis ──────────────────────────────────────────────
    mtf_enabled: bool = True

    # ── S/R detector ─────────────────────────────────────────────────────────
    sr_swing_window: int = 5
    sr_max_levels: int = 8

    # ── Professional aggregator ───────────────────────────────────────────────
    use_professional_aggregator: bool = True

    # ── Signal persistence ────────────────────────────────────────────────────
    signal_persistence_enabled: bool = True

    # ── App ───────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    loop_interval_seconds: int = 60


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
