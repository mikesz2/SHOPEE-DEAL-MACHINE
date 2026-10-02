from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'windows'
    app_host: str = '127.0.0.1'
    app_port: int = 8787
    app_timezone: str = 'America/Bahia'
    log_level: str = 'INFO'
    app_require_auth: bool = True
    admin_user: str = 'admin'
    admin_password: str = ''
    session_hours: int = 12
    app_session_secret: str = ''
    cookie_secure: bool = False
    public_base_url: str = ''

    shopee_app_id: str = ''
    shopee_secret: str = ''
    shopee_api_url: str = 'https://open-api.affiliate.shopee.com.br/graphql'

    evolution_url: str = ''
    evolution_api_key: str = ''
    evolution_instance: str = 'deal-machine'
    telegram_bot_token: str = '' 
    telegram_target_chat: str = ''
    telegram_admin_chat: str = ''
    telegram_api_id: int | None = None
    telegram_api_hash: str = ''
    telegram_phone: str = ''
    telegram_reader_enabled: bool = True
    telegram_session_path: str = 'data/telegram/reader'

    database_url: str = 'sqlite:///./data/windows/deals.db'
    redis_url: str = ''
    redis_required: bool = False

    worker_poll_seconds: int = 10
    shopee_request_timeout_seconds: int = 25
    http_max_retries: int = 3
    backup_interval_hours: int = 12
    backup_retention_days: int = 30

    @field_validator('telegram_api_id', mode='before')
    @classmethod
    def _blank_optional_int(cls, v):
        return None if v is None or str(v).strip() == '' else v

    @property
    def telegram_session_parent(self) -> Path:
        return Path(self.telegram_session_path).parent

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {'production', 'prod', 'windows'}

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith('sqlite')


settings = Settings()
