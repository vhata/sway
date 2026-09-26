"""Bounded HTTP input and conservative socket-peer rate limits."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sway.hosting.runtime import RateLimiter, WebConfig


class HostedBoundary:
    def __init__(self, app: ASGIApp, config: WebConfig, limiter: RateLimiter) -> None:
        self.app = app
        self.config = config
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        mutation = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if headers.get("host", "").lower() != self.config.canonical_host:
            await PlainTextResponse("Unknown host.", 400)(scope, receive, send)
            return
        if mutation and (
            headers.get("origin") != self.config.origin
            or headers.get("sec-fetch-site") == "cross-site"
        ):
            await PlainTextResponse("This request must come from this site.", 403)(
                scope, receive, send
            )
            return
        peer = scope.get("client")
        address = peer[0] if peer else "unknown"
        credential = scope["path"] in {"/identity", "/recover"} or scope["path"].startswith(
            "/join/"
        )
        # Include unauthenticated page loads: they can mint an anonymous session.
        category = "credentials" if credential else "mutations" if mutation else "reads"
        limit = (
            self.config.credential_requests_per_minute
            if credential
            else self.config.mutation_requests_per_minute
            if mutation
            else 300
        )
        public_asset = not mutation and scope["path"].startswith("/static/")
        if not public_asset and not self.limiter.allow(address, category, limit):
            await PlainTextResponse(
                "Too many requests. Please wait a minute.", 429, headers={"Retry-After": "60"}
            )(scope, receive, send)
            return
        body = bytearray()
        if mutation:
            if (
                headers.get("content-type", "").split(";", 1)[0]
                != "application/x-www-form-urlencoded"
            ):
                await PlainTextResponse("Use a form to submit this request.", 415)(
                    scope, receive, send
                )
                return
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.config.max_request_bytes:
                    await PlainTextResponse("This request is too large.", 413)(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break

        consumed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            if mutation and not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def private_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                values = list(message.get("headers", []))
                values.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"same-origin"),
                        (b"x-content-type-options", b"nosniff"),
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
                        ),
                        (b"strict-transport-security", b"max-age=31536000"),
                    ]
                )
                message["headers"] = values
            await send(message)

        await self.app(scope, bounded_receive, private_send)
