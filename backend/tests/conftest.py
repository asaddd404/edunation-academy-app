"""Settings the app requires at import time.

`app.config.Settings` is constructed at module import, so anything that
reaches `app.database` (the schemas do, via the ORM enums) needs these
present before the import happens. No test here opens a connection --
these values only have to be well-formed.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
