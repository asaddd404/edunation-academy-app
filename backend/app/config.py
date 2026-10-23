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
    # Every /api request, per client address. Generous on purpose: a whole
    # classroom shares one NAT address, and thirty students clicking through
    # lessons make a few requests per second between them. This stops a
    # script or a runaway tab, not a busy class.
    api_rate_limit_per_minute: int = 600
    # In-flight requests one worker accepts before answering 503 at once. On
    # a 1-CPU / 2 GB server a backlog does not get served faster by queueing
    # -- it waits on the same five DB connections, holds memory, and times
    # out anyway. Shedding early keeps the requests already admitted fast.
    # Sized by load-testing 200 students on a 1-CPU replica (loadtest/):
    # 64 let the backlog wait out the 5 s pool timeout and end in errors; 32
    # shed so eagerly that retries ran out (0.5% of actions failed); 48 kept
    # failures at 0.2% with p95 under 2 s -- the excess gets an instant 503
    # that the client retries.
    max_inflight_requests: int = 48

    # --- resource ceilings --------------------------------------------------
    # pool_size + max_overflow, times the uvicorn worker count, has to stay
    # under Postgres max_connections (100 by default). Two workers x 10 = 20.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # Short on purpose: a request that cannot get a connection should fail
    # fast rather than hold a worker for the 30-second default while the
    # queue behind it grows.
    db_pool_timeout_seconds: int = 5
    # Ceiling on any single query. Above every legitimate query here, below
    # the point where a stuck one has taken the pool down with it.
    db_statement_timeout_ms: int = 15_000
    db_idle_tx_timeout_ms: int = 30_000

    # Redis is on the request path for rate limiting, so a *hung* Redis --
    # not refusing, just never answering -- would hang every request that
    # consults it. The limiter is written to fail open, but it can only do
    # that if the call actually returns.
    redis_socket_timeout_seconds: float = 2.0

    # Kill switch for the single most expensive endpoint in the app. Set to
    # false and restart to shed that load during an incident while the rest
    # of the site keeps serving lessons -- a runbook step is only real if
    # there is something to turn.
    ent_pdf_import_enabled: bool = True

    # How long a second import waits for the single parsing slot before it is
    # refused. Sized against the measured job: a heavy book takes ~10 s, so 5
    # seconds would turn the second teacher of the morning into a 429 on a
    # perfectly legitimate action. 30 seconds lets two or three queue and
    # still bounds the wait -- the point of the limit is to stop a pile-up,
    # not to make the feature unreliable for the people it is for.
    pdf_import_queue_wait_seconds: float = 30.0

    # How long a cached leaderboard stays warm. The board is an aggregate
    # over every submitted attempt; recomputing it per request is the
    # classic way an app denies service to itself.
    leaderboard_cache_seconds: int = 60

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
