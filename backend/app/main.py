import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import settings
from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware

# Without this, the root logger defaults to WARNING and every app-side
# logger.info() call (e.g. the ЕНТ PDF import debug dump) is silently
# dropped before it ever reaches a handler -- nothing in this project
# configured logging before now.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# The interactive docs enumerate every endpoint and its schema for anyone who
# asks. Useful locally, an unnecessary map of the attack surface in production.
app = FastAPI(
    title="Edunation Academy API",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# Registration order is inside-out: the last one added wraps the others, so
# CORS below stays outermost (its headers must survive on error responses
# too), then the body-size gate, then the header stamper closest to the app.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
