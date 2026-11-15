"""
ASGI request-size protection for the notification receiver.

Rejects notification requests larger than 8 KB.
"""

from starlette.responses import PlainTextResponse


class RequestSizeLimit:
    def __init__(self, app, max_bytes: int = 8192):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("path") != "/api/v1/notifications"
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")

        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    await self.reject(scope, receive, send)
                    return
            except ValueError:
                await PlainTextResponse(
                    "Invalid Content-Length",
                    status_code=400,
                )(scope, receive, send)
                return

        body = bytearray()

        while True:
            message = await receive()

            if message["type"] == "http.disconnect":
                return

            if message["type"] != "http.request":
                continue

            body.extend(message.get("body", b""))

            if len(body) > self.max_bytes:
                await self.reject(scope, receive, send)
                return

            if not message.get("more_body", False):
                break

        delivered = False

        async def replay_receive():
            nonlocal delivered

            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": False,
                }

            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def reject(scope, receive, send):
        response = PlainTextResponse(
            "Request body too large",
            status_code=413,
        )
        await response(scope, receive, send)