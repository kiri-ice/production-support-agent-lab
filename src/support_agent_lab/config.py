from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_tenant_id: str = "demo_tenant"
    app_model_provider: str = "mock"
    app_database_url: str = "sqlite:///./data/local/support-agent-lab.db"
    app_enable_mcp: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

