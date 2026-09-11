from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    simulation_service_url: str = "http://dev.htcmc.site"
    polling_interval_seconds: float = 3
    request_timeout_seconds: float = 30

    model_config = SettingsConfigDict(env_prefix="DASHBOARD_", env_file=".env")
