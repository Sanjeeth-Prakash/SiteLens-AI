"""Count public demo analyses in a shared UTC-day counter."""

import os
from datetime import datetime, timedelta, timezone
from math import ceil

import httpx

QUOTA_UNAVAILABLE = "The demo usage counter is unavailable. You can still open the example report."
RESERVE = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
if used >= tonumber(ARGV[1]) then
    return 0
end
if redis.call('INCR', KEYS[1]) == 1 then
    redis.call('EXPIRE', KEYS[1], 172800)
end
return 1
"""


class QuotaUnavailable(RuntimeError):
    """The quota could not be checked reliably."""


class QuotaReached(RuntimeError):
    def __init__(self, retry_after: int):
        super().__init__("The live analysis limit has been reached. Try again after the daily reset or open the example report.")
        self.retry_after = retry_after


def reserve_analysis() -> None:
    """Reserve an analysis before calling the model when the demo cap is enabled."""
    configured_limit = os.getenv("SITELENS_DAILY_ANALYSIS_LIMIT", "").strip()
    if not configured_limit:
        return
    try:
        limit = int(configured_limit)
        if limit < 1:
            raise ValueError("Expected a positive daily limit")
    except ValueError as exc:
        raise QuotaUnavailable(QUOTA_UNAVAILABLE) from exc

    endpoint = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    try:
        url = httpx.URL(endpoint)
    except httpx.InvalidURL as exc:
        raise QuotaUnavailable(QUOTA_UNAVAILABLE) from exc
    if not (
        token
        and url.scheme == "https"
        and url.host.endswith(".upstash.io")
        and url.port is None
        and not (url.userinfo or url.query or url.fragment)
        and url.path == "/"
    ):
        raise QuotaUnavailable(QUOTA_UNAVAILABLE)

    now = datetime.now(timezone.utc)
    key = f"sitelens:analysis:{now.date().isoformat()}"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=["EVAL", RESERVE, 1, key, limit],
            timeout=4,
            trust_env=False,
        )
        response.raise_for_status()
        result = response.json()["result"]
        if type(result) is not int or result not in (0, 1):
            raise ValueError("Unexpected quota store response")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise QuotaUnavailable(QUOTA_UNAVAILABLE) from exc
    if result == 0:
        reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        raise QuotaReached(max(1, ceil((reset - now).total_seconds())))
