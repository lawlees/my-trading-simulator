"""
Simple in-memory rate limiter for the notification API.

Allows up to 30 requests per minute per client IP.
Intended for a single-process deployment.
"""

import threading
import time
from collections import defaultdict, deque

from starlette.responses import PlainTextResponse


class RateLimitMiddleware:
    def __init__(
        self,
        app,
        max_requests: int = 30,
        window_seconds: int = 60,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        self.requests = defaultdict(deque)
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("path") != "/api/v1/notifications"
        ):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        now = time.monotonic()

        with self.lock:
            timestamps = self.requests[client_ip]

            while (
                timestamps
                and now - timestamps[0] >= self.window_seconds
            ):
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                allowed = False
            else:
                timestamps.append(now)
                allowed = True

        if not allowed:
            response = PlainTextResponse(
                "Too Many Requests",
                status_code=429,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)