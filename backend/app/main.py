import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.api import api_router
from app.config import settings
from app.core.middleware import BodySizeLimitMiddleware, LoadSheddingMiddleware, SecurityHeadersMiddleware

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
# too), then load shedding, the body-size gate, and the header stamper
# closest to the app.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
# Outside the body-size gate so a flood is turned away before anything else
# runs; inside CORS so a 429/503 still carries the headers the browser needs
# to show it.
app.add_middleware(LoadSheddingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# Text the database itself refuses: a value longer than its column, or a
# character Postgres cannot store (NUL). Schemas are meant to stop both
# first, and now do for every field found -- this is the net under any field
# still missed, so the user gets a sentence and a 422 instead of a 500.
_DB_TEXT_ERRORS = {
    "StringDataRightTruncationError": "Слишком длинное значение в одном из полей.",
    "CharacterNotInRepertoireError": "Текст содержит недопустимые символы.",
    "UntranslatableCharacterError": "Текст содержит недопустимые символы.",
}


@app.exception_handler(DBAPIError)
async def _db_text_error(request: Request, exc: DBAPIError):
    cause = getattr(exc.orig, "__cause__", None) or exc.orig
    message = _DB_TEXT_ERRORS.get(type(cause).__name__)
    if message is None:
        raise exc
    logging.getLogger(__name__).warning("Refused text at %s: %s", request.url.path, type(cause).__name__)
    return JSONResponse({"detail": message}, status_code=422)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
