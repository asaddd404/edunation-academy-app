from redis.asyncio import Redis, from_url

from app.config import settings

# Timeouts are the point of this file.
#
# Redis sits on the request path for rate limiting, and `RateLimit.hit`
# deliberately fails open so that a Redis outage does not stop people
# logging in. That only works for an outage Redis *reports*: a connection
# refused raises immediately and is caught. A Redis that accepts the
# connection and then never answers -- swapping, blocked on a slow command,
# a half-open socket after a network blip -- would leave every request
# waiting forever, with no exception to catch and nothing to fail open to.
# The socket timeouts turn that silence back into an error the limiter can
# handle.
#
# `health_check_interval` re-validates idle pooled connections, so a socket
# that died while nothing was using it is discovered before a user's request
# is the thing that finds out.
redis_client: Redis = from_url(
    settings.redis_url,
    decode_responses=True,
    socket_timeout=settings.redis_socket_timeout_seconds,
    socket_connect_timeout=settings.redis_socket_timeout_seconds,
    health_check_interval=30,
)
