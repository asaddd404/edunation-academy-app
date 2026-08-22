from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "development" | "production". Guards anything that must never run
    # against live data (the demo seeder wipes every table it owns) and
    # switches on production-only response headers such as HSTS.
    env: str = "development"

    database_url: str
    redis_url: str

    jwt_secret: str
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    video_ticket_ttl_minutes: int = 180

    cors_origins: str = "http://localhost,http://localhost:5173"

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
