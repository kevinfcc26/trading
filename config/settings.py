from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database (individual fields — URL is assembled automatically)
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

    # Anthropic
    anthropic_api_key: SecretStr

    # MetaTrader 5
    mt5_login: int = 0
    mt5_password: SecretStr = SecretStr("")
    mt5_server: str = ""

    # Trading defaults
    default_symbol: str = "EURUSD"
    default_timeframe: str = "H1"
    dry_run: bool = True

    # Risk
    risk_per_trade: float = 0.01
    max_open_positions: int = 3

    # Signal weights (must sum to 1.0)
    weight_ta: float = 0.25
    weight_ml: float = 0.35
    weight_claude: float = 0.40
    min_signal_threshold: float = 0.60
    claude_veto_threshold: float = 0.70

    # App
    log_level: str = "INFO"
    loop_interval_seconds: int = 60


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
