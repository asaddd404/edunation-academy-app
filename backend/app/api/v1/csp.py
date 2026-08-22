"""Collector for Content-Security-Policy violation reports.

The policy in the Caddyfile ships as `Report-Only` and points here. Without a
live endpoint the reports are simply lost, and the policy can never be turned
on with any confidence about what it would break.

Unauthenticated by necessity -- the browser posts these on its own, with no
session -- so it is rate-limited by address and the body is truncated before
anything is written. The report is attacker-controlled text: it is logged as
data and never interpreted.
"""

import json
import logging

from fastapi import APIRouter, Request, Response, status

from app.core.rate_limit import RateLimit, request_ip

router = APIRouter(tags=["csp"])
logger = logging.getLogger("edunation.csp")

_MAX_REPORT_BYTES = 8 * 1024
CSP_REPORT_BY_IP = RateLimit("csp_report_ip", limit=60, window_seconds=60)


@router.post("/csp-report", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def receive_csp_report(request: Request) -> Response:
    allowed, _ = await CSP_REPORT_BY_IP.hit(request_ip(request))
    if not allowed:
        # 204 rather than 429: the browser does not retry either way, and a
        # visible error here would be noise in every user's console.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raw = (await request.body())[:_MAX_REPORT_BYTES]
    try:
        report = json.loads(raw or b"{}")
    except ValueError:
        logger.info("CSP report (unparseable): %r", raw[:512])
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    body = report.get("csp-report", report)
    if isinstance(body, dict):
        # Only the fields that say what to change in the policy. Logging the
        # whole document would pull in the full page URL, which carries ids
        # and, on some routes, the video ticket.
        logger.info(
            "CSP violation: directive=%r blocked=%r",
            str(body.get("violated-directive") or body.get("effectiveDirective"))[:200],
            str(body.get("blocked-uri") or body.get("blockedURL"))[:300],
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
