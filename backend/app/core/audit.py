"""Append-only record of privileged and destructive actions.

Kept on its own logger (`edunation.audit`) rather than mixed into the
application log, so it can be routed to a separate sink and retained on a
different schedule. Everything an incident review needs has to be on one
line: who, what, how much, when, and from where -- an entry that says
"bulk delete happened" and nothing else answers no question worth asking.

Deliberately not a database table: the actions recorded here include
deleting rows, and a log that lives in the same database as the data it
describes is exactly the log an attacker with write access edits.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from app.core.client_ip import client_ip

logger = logging.getLogger("edunation.audit")


def audit_log(
    action: str,
    *,
    actor_id: int | None,
    actor_role: str | None = None,
    request: Request | None = None,
    **details: Any,
) -> None:
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "ip": client_ip(request) if request is not None else None,
    }
    entry.update(details)
    # `default=str` so an unexpected value (an enum, a date) degrades to its
    # text form instead of losing the whole entry to a serialization error.
    logger.info("%s", json.dumps(entry, ensure_ascii=False, default=str))
