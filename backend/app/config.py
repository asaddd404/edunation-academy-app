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

    # Rate limiting reads the caller's address from X-Forwarded-For, but only
    # when the request actually arrived from one of these peers -- otherwise
    # any client could spoof the header and step out of every IP-keyed limit.
    # The compose network's private ranges cover Caddy/nginx sitting in front.
    trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    rate_limit_enabled: bool = True

    # Hard ceiling on a request body, enforced in-process. The edge (Caddy /
    # nginx) has its own, larger cap for video uploads; this one stops a
    # JSON body from being read into memory unbounded.
    max_request_body_bytes: int = 25 * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.env.strip().lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_networks(self) -> list:
        import ipaddress

        networks = []
        for raw in self.trusted_proxy_cidrs.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                networks.append(ipaddress.ip_network(raw, strict=False))
            except ValueError:
                continue
        return networks


settings = Settings()
