"""Bounded pools for the CPU-heavy work this app does inside a request.

Measured, not guessed: a 400-page ЕНТ book -- 0.35 MB, well under the 15 MB
upload cap -- costs 10.6 seconds of single-threaded CPU to extract and parse
on a developer laptop. Production runs two uvicorn workers on one vCPU, so
the size limit is close to meaningless as a cost control: what decides the
bill is the page count, and a small file can carry a lot of pages.

Without a bound, `asyncio.to_thread` hands this work to the default executor,
which is `min(32, cpu_count + 4)` threads wide and shared with everything
else. Ten simultaneous imports -- inside the 10/hour rate limit, which counts
requests and says nothing about how many run at once -- put ~100 seconds of
CPU on a one-vCPU box. The site does not crash; it stops answering, logins
included, which is worse because nothing restarts and nothing alerts.

So each kind of heavy work gets its own small pool and its own queue, and a
caller that cannot get a slot quickly is turned away with 429 rather than
left to pile up. Turning one teacher's import away keeps the other thousand
users' pages answering.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BoundedWorkPool:
    """Runs blocking work on a fixed number of threads, refusing overflow.

    The semaphore and the executor are sized together on purpose. The
    executor alone would queue excess work invisibly -- requests would sit
    waiting with no upper bound on how long, which is the failure mode this
    exists to prevent, just moved somewhere harder to see.
    """

    def __init__(self, name: str, max_concurrent: int, queue_wait_seconds: float) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.queue_wait_seconds = queue_wait_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix=name)

    async def run(self, fn: Callable[..., T], *args: Any, timeout: float) -> T:
        """Acquires a slot, runs `fn(*args)` off the event loop, returns its result.

        Raises 429 if no slot frees up within `queue_wait_seconds`, and
        `asyncio.TimeoutError` if the work itself outlives `timeout`.

        Note what the timeout does and does not do: it frees the *request*,
        not the CPU. A Python thread cannot be killed from outside, so a
        timed-out parse keeps its slot until it finishes on its own. That is
        acceptable only because the work is separately bounded -- the page and
        character caps in `ent_pdf_import` mean it cannot run forever. Remove
        those caps and this stops being safe.
        """
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.queue_wait_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "%s pool saturated (%d slots busy), shedding a request", self.name, self.max_concurrent
            )
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Сервер сейчас занят обработкой других файлов. Попробуйте через минуту.",
                headers={"Retry-After": "60"},
            )

        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(loop.run_in_executor(self._executor, fn, *args), timeout=timeout)
        finally:
            self._semaphore.release()


class ConcurrencyGate:
    """A slot limiter for work that is already off the event loop.

    ffmpeg is its own process, so it never blocks the loop -- but it will
    happily take the whole vCPU, and nothing stopped a teacher from starting
    five transcodes at once. This bounds how many run, without owning any
    threads itself.
    """

    def __init__(self, name: str, max_concurrent: int) -> None:
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self) -> None:
        if self._semaphore.locked():
            logger.info("%s gate full, work will wait for a slot", self.name)
        await self._semaphore.acquire()

    async def __aexit__(self, *exc: Any) -> None:
        self._semaphore.release()


# One at a time, but with room to queue. Widening to two would halve each
# import's share of the single production core, which is the resource being
# protected; lengthening the queue costs nothing but a teacher's patience.
# A heavy book measures ~10 s, so the default 30 s wait admits two or three
# before anyone is turned away.
PDF_IMPORT_POOL = BoundedWorkPool(
    "pdf-import",
    max_concurrent=1,
    queue_wait_seconds=settings.pdf_import_queue_wait_seconds,
)

# Transcoding is minutes long, so the queue here is unbounded in time on
# purpose: the upload has already been accepted and the work runs after the
# response: making a teacher's video fail because another was still encoding
# would lose the upload for no gain.
VIDEO_TRANSCODE_GATE = ConcurrencyGate("video-transcode", max_concurrent=1)
