"""Measure application response time and compress catalogue JSON."""

from time import perf_counter

from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware


class PerformanceMiddleware:
    def __init__(self, app):
        self.app = app
        self.compressed_app = GZipMiddleware(app, minimum_size=1000, compresslevel=4)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        started = perf_counter()

        async def timed_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("Server-Timing", f"app;dur={(perf_counter() - started) * 1000:.1f}")
            await send(message)

        # Compress the large catalogue responses; avoid spending CPU compressing
        # uploaded photos or responses containing locker codes and credentials.
        app = self.compressed_app if scope["path"] in ("/items", "/items/all", "/items/groups", "/items/groups/all") else self.app
        await app(scope, receive, timed_send)
